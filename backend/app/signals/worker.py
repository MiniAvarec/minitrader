"""Signal worker — strategy-aware, multi-exchange.

On every `kline_closed` event (which now carries exchange + symbol + tf), we
ask: for each user that has this (exchange, symbol) in their watchlist, which
strategy do they have selected? Evaluate that strategy.

Defaults: if a user has no per-pair selection, we fall back to the built-in
`multi_tf_confluence` strategy.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.data.calendar import is_in_blackout
from app.data.redis_io import (
    SIGNAL_CHANNEL,
    get_klines,
    make_redis,
    publish_signal,
    subscribe,
)
from app.db.models import (
    NewsItem,
    Signal as SignalModel,
    SignalSide,
    Strategy,
    User,
    UserStrategySelection,
    UserWatchlistEntry,
)
from app.db.session import SessionLocal
from app.signals.dsl.loader import load_yaml_text
from app.signals.engine import evaluate

log = logging.getLogger("signals")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

DEFAULT_BUILTIN_SLUG = "multi_tf_confluence"
COOLDOWN_KEY_FMT = "signal_cooldown:{user_id}:{exchange}:{symbol}:{strategy_id}"


async def _recent_news(symbol: str) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(NewsItem)
                .where(NewsItem.published_at >= cutoff)
                .order_by(NewsItem.published_at.desc())
                .limit(50)
            )
        ).scalars().all()
    out: list[dict] = []
    for n in rows:
        if symbol in (n.symbols or []):
            out.append(
                {
                    "source": n.source,
                    "headline": n.headline,
                    "url": n.url,
                    "sentiment": n.sentiment,
                    "published_at": n.published_at,
                }
            )
    return out


async def _calendar_blackout(r) -> bool:
    raw = await r.get("calendar:high_impact")
    if not raw:
        return False
    try:
        events = json.loads(raw)
    except Exception:
        return False
    return is_in_blackout(events, datetime.now(timezone.utc))


async def _fear_greed_value(r) -> float | None:
    raw = await r.get("market:fear_greed")
    if not raw:
        return None
    try:
        return float(json.loads(raw).get("value"))
    except (ValueError, TypeError):
        return None


async def _reddit_hype_score(r, symbol: str) -> float | None:
    raw = await r.get(f"reddit_hype:{symbol}")
    if not raw:
        return None
    try:
        return float(json.loads(raw).get("score"))
    except (ValueError, TypeError):
        return None


async def _user_strategy_for(
    db, user: User, exchange: str, symbol: str
) -> Strategy | None:
    sel = (
        await db.execute(
            select(UserStrategySelection)
            .where(UserStrategySelection.user_id == user.id)
            .where(UserStrategySelection.exchange == exchange)
            .where(UserStrategySelection.symbol == symbol)
            .where(UserStrategySelection.enabled.is_(True))
        )
    ).scalar_one_or_none()
    if sel is not None:
        return (
            await db.execute(select(Strategy).where(Strategy.id == sel.strategy_id))
        ).scalar_one_or_none()
    return (
        await db.execute(
            select(Strategy)
            .where(Strategy.user_id.is_(None))
            .where(Strategy.slug == DEFAULT_BUILTIN_SLUG)
        )
    ).scalar_one_or_none()


async def _evaluate_for_user(
    r, db, user: User, exchange: str, symbol: str, tfs: list[str]
) -> None:
    strategy = await _user_strategy_for(db, user, exchange, symbol)
    if strategy is None:
        return
    try:
        strat_def = load_yaml_text(strategy.code)
    except Exception as e:
        log.warning("strategy %s yaml invalid: %s", strategy.id, e)
        return

    cooldown_key = COOLDOWN_KEY_FMT.format(
        user_id=user.id, exchange=exchange, symbol=symbol, strategy_id=strategy.id
    )
    last_raw = await r.get(cooldown_key)
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw)
            if (datetime.now(timezone.utc) - last) < timedelta(minutes=strat_def.cooldown_min):
                return
        except Exception:
            pass

    needed_tfs = sorted(set(tfs) | set(strat_def.timeframes))
    tf_klines = {
        tf: await get_klines(r, exchange, symbol, tf) for tf in needed_tfs
    }
    blackout = await _calendar_blackout(r)
    news = await _recent_news(symbol)
    fear_greed = await _fear_greed_value(r)
    reddit_hype = await _reddit_hype_score(r, symbol)

    sig = evaluate(
        symbol,
        tf_klines,
        strategy=strat_def,
        news=news,
        blackout=blackout,
        fear_greed=fear_greed,
        reddit_hype=reddit_hype,
    )
    if sig is None:
        return

    row = SignalModel(
        user_id=user.id,
        strategy_id=strategy.id,
        exchange=exchange,
        symbol=sig.symbol,
        side=SignalSide.buy if sig.side == "buy" else SignalSide.sell,
        confidence=sig.confidence,
        entry=sig.entry,
        sl=sig.sl,
        tp=sig.tp,
        breakdown=[b.model_dump() for b in sig.breakdown],
        news_refs=sig.news_refs,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    payload = {
        "event": "signal",
        "id": row.id,
        "user_id": user.id,
        "strategy_id": strategy.id,
        "strategy_name": strategy.name,
        "exchange": exchange,
        **sig.model_dump(mode="json"),
    }
    await publish_signal(r, payload)
    await r.set(
        cooldown_key,
        datetime.now(timezone.utc).isoformat(),
        ex=strat_def.cooldown_min * 60,
    )
    log.info(
        "signal user=%s %s:%s strategy=%s side=%s conf=%.1f",
        user.id,
        exchange,
        symbol,
        strategy.slug,
        sig.side,
        sig.confidence,
    )


async def _evaluate_pair(r, exchange: str, symbol: str, tfs: list[str]) -> None:
    """Find users watching (exchange, symbol) and evaluate their strategy."""
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(User)
                .join(UserWatchlistEntry, UserWatchlistEntry.user_id == User.id)
                .where(UserWatchlistEntry.exchange == exchange)
                .where(UserWatchlistEntry.symbol == symbol)
                .where(UserWatchlistEntry.enabled.is_(True))
            )
        ).scalars().all()
        for user in rows:
            try:
                await _evaluate_for_user(r, db, user, exchange, symbol, tfs)
            except Exception as e:
                log.warning(
                    "evaluate user=%s %s:%s failed: %s", user.id, exchange, symbol, e
                )


async def main() -> None:
    s = get_settings()
    r = make_redis()
    pubsub = await subscribe(r, [SIGNAL_CHANNEL])
    log.info("signals worker subscribed; timeframes=%s", s.default_timeframes)
    async for msg in pubsub.listen():
        if msg.get("type") != "message":
            continue
        try:
            data = json.loads(msg["data"])
        except Exception:
            continue
        if data.get("event") != "kline_closed":
            continue
        exchange = data.get("exchange") or "binance"
        symbol = data.get("symbol")
        if not symbol:
            continue
        try:
            await _evaluate_pair(r, exchange, symbol, s.default_timeframes)
        except Exception as e:
            log.warning("evaluate %s:%s failed: %s", exchange, symbol, e)


if __name__ == "__main__":
    asyncio.run(main())
