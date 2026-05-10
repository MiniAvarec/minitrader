"""Polling worker: pulls news from Finnhub, CryptoPanic; calendar; persists + publishes."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.data.calendar import fetch_high_impact
from app.data.cryptopanic import fetch_news as fetch_cryptopanic
from app.data.finnhub import fetch_crypto_news as fetch_finnhub
from app.data.redis_io import make_redis, publish_news
from app.db.models import NewsItem
from app.db.session import SessionLocal

log = logging.getLogger("news_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

NEWS_INTERVAL_S = 120
CALENDAR_INTERVAL_S = 60 * 30


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
    while True:
        try:
            items: list[dict] = []
            items += await fetch_finnhub()
            items += await fetch_cryptopanic()
            n = await _persist_and_publish(items, r)
            log.info("news fetched=%d new=%d", len(items), n)
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


async def main() -> None:
    r = make_redis()
    await asyncio.gather(_news_loop(r), _calendar_loop(r))


if __name__ == "__main__":
    asyncio.run(main())
