"""Polling worker: pulls news from multiple sources, persists, publishes.

Pipelines:
  - news       : Finnhub, CryptoPanic, CryptoCompare, GDELT, NewsData.io
                 (NewsData gated to every 5th cycle to stay under 200/day quota)
  - calendar   : economic-calendar high-impact events (existing)
  - fear/greed : alternative.me Crypto F&G index, hourly
  - reddit hype: per-symbol community mention scores, every 5 min

Each signal pipeline writes a Redis cache key the DSL reads (`market:fear_greed`,
`reddit_hype:<SYMBOL>`) so strategy evaluation doesn't need a DB round-trip.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.data.calendar import fetch_high_impact
from app.data.cryptocompare import fetch_news as fetch_cryptocompare
from app.data.cryptopanic import fetch_news as fetch_cryptopanic
from app.data.feargreed import fetch_index as fetch_fear_greed
from app.data.finnhub import fetch_crypto_news as fetch_finnhub
from app.data.gdelt import fetch_news as fetch_gdelt
from app.data.newsdata import fetch_news as fetch_newsdata
from app.data.reddit_hype import fetch_hype as fetch_reddit_hype
from app.data.redis_io import make_redis, publish_news
from app.db.models import MarketSentiment, NewsItem, RedditHype
from app.db.session import SessionLocal

log = logging.getLogger("news_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

NEWS_INTERVAL_S = 120
CALENDAR_INTERVAL_S = 60 * 30
FEAR_GREED_INTERVAL_S = 60 * 60          # 1h (index updates daily)
REDDIT_HYPE_INTERVAL_S = 60 * 5          # 5 min
NEWSDATA_EVERY_NTH = 5                   # 120s × 5 = 10 min => 144/day under 200 cap

FEAR_GREED_REDIS_KEY = "market:fear_greed"
REDDIT_HYPE_REDIS_PREFIX = "reddit_hype:"
REDDIT_HYPE_TTL_S = 60 * 15              # 3× the poll interval


async def _persist_and_publish(items: list[dict], r) -> int:
    if not items:
        return 0
    inserted = 0
    async with SessionLocal() as db:
        for it in items:
            stmt = pg_insert(NewsItem).values(
                source=it["source"],
                external_id=it["external_id"],
                headline=it["headline"][:500],
                url=it["url"][:1000],
                symbols=it["symbols"],
                sentiment=it["sentiment"],
                published_at=it["published_at"],
                fetched_at=datetime.now(timezone.utc),
            ).on_conflict_do_nothing(index_elements=["source", "external_id"])
            try:
                res = await db.execute(stmt)
                if res.rowcount:
                    inserted += 1
                    await publish_news(
                        r,
                        {
                            "source": it["source"],
                            "headline": it["headline"],
                            "url": it["url"],
                            "symbols": it["symbols"],
                            "sentiment": it["sentiment"],
                            "published_at": it["published_at"].isoformat(),
                        },
                    )
            except IntegrityError:
                await db.rollback()
        await db.commit()
    return inserted


async def _news_loop(r) -> None:
    cycle = 0
    while True:
        try:
            cycle += 1
            items: list[dict] = []
            items += await fetch_finnhub()
            items += await fetch_cryptopanic()
            items += await fetch_cryptocompare()
            items += await fetch_gdelt()
            # NewsData.io has a tight free-tier budget; throttle here.
            if cycle % NEWSDATA_EVERY_NTH == 1:
                items += await fetch_newsdata()
            n = await _persist_and_publish(items, r)
            log.info("news fetched=%d new=%d cycle=%d", len(items), n, cycle)
        except Exception as e:
            log.warning("news loop error: %s", e)
        await asyncio.sleep(NEWS_INTERVAL_S)


async def _calendar_loop(r) -> None:
    while True:
        try:
            events = await fetch_high_impact()
            await r.set("calendar:high_impact", json.dumps(events), ex=CALENDAR_INTERVAL_S * 2)
            log.info("calendar high-impact events=%d", len(events))
        except Exception as e:
            log.warning("calendar loop error: %s", e)
        await asyncio.sleep(CALENDAR_INTERVAL_S)


async def _fear_greed_loop(r) -> None:
    while True:
        try:
            idx = await fetch_fear_greed()
            if idx is not None:
                async with SessionLocal() as db:
                    db.add(MarketSentiment(
                        source="fear_greed",
                        value=idx["value"],
                        classification=idx["classification"],
                        fetched_at=idx["fetched_at"],
                    ))
                    await db.commit()
                await r.set(
                    FEAR_GREED_REDIS_KEY,
                    json.dumps({
                        "value": idx["value"],
                        "classification": idx["classification"],
                        "fetched_at": idx["fetched_at"].isoformat(),
                    }),
                    ex=FEAR_GREED_INTERVAL_S * 3,
                )
                log.info("fear_greed value=%.1f (%s)", idx["value"], idx["classification"])
            else:
                log.info("fear_greed fetch returned no data")
        except Exception as e:
            log.warning("fear_greed loop error: %s", e)
        await asyncio.sleep(FEAR_GREED_INTERVAL_S)


async def _reddit_hype_loop(r) -> None:
    while True:
        try:
            hype = await fetch_reddit_hype()
            if hype:
                async with SessionLocal() as db:
                    for symbol, data in hype.items():
                        stmt = pg_insert(RedditHype).values(
                            symbol=symbol,
                            score=data["score"],
                            mentions_60m=data["mentions_60m"],
                            upvotes_60m=data["upvotes_60m"],
                            updated_at=data["fetched_at"],
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["symbol"],
                            set_={
                                "score": stmt.excluded.score,
                                "mentions_60m": stmt.excluded.mentions_60m,
                                "upvotes_60m": stmt.excluded.upvotes_60m,
                                "updated_at": stmt.excluded.updated_at,
                            },
                        )
                        await db.execute(stmt)
                    await db.commit()
                pipe = r.pipeline()
                for symbol, data in hype.items():
                    pipe.set(
                        f"{REDDIT_HYPE_REDIS_PREFIX}{symbol}",
                        json.dumps({
                            "score": data["score"],
                            "mentions_60m": data["mentions_60m"],
                            "upvotes_60m": data["upvotes_60m"],
                        }),
                        ex=REDDIT_HYPE_TTL_S,
                    )
                await pipe.execute()
                top = max(hype.items(), key=lambda kv: kv[1]["score"])
                log.info(
                    "reddit_hype symbols=%d top=%s score=%.2f",
                    len(hype), top[0], top[1]["score"],
                )
            else:
                log.info("reddit_hype no mentions in window")
        except Exception as e:
            log.warning("reddit_hype loop error: %s", e)
        await asyncio.sleep(REDDIT_HYPE_INTERVAL_S)


async def main() -> None:
    r = make_redis()
    await asyncio.gather(
        _news_loop(r),
        _calendar_loop(r),
        _fear_greed_loop(r),
        _reddit_hype_loop(r),
    )


if __name__ == "__main__":
    asyncio.run(main())
