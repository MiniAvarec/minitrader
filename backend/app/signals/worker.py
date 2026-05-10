"""Signal worker — strategy-aware version.

On every `kline_closed` event, we ask: for each user that's tracking this
symbol, which strategy do they have selected? Evaluate that strategy.

Defaults: if a user has no per-symbol selection, we fall back to the
built-in `multi_tf_confluence` strategy.

Each fired signal is persisted with `user_id` + `strategy_id` and published
to redis with the same keys, so downstream workers (Telegram, executor) can
route it to the right user.
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
)
from app.db.session import SessionLocal
from app.signals.dsl.loader import load_yaml_text
from app.signals.engine import evaluate

log = logging.getLogger("signals")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

DEFAULT_BUILTIN_SLUG = "multi_tf_confluence"
COOLDOWN_KEY_FMT = "signal_cooldown:{user_id}:{symbol}:{strategy_id}"


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


async def _user_strategy_for(db, user: User, symbol: str) -> Strategy | None:
    sel = (
        await db.execute(
            select(UserStrategySelection)
            .where(UserStrategySelection.user_id == user.id)
            .where(UserStrategySelection.symbol == symbol)
            .where(UserStrategySelection.enabled.is_(True))
        )
    ).scalar_one_or_none()
    if sel is not None:
        return (
            await db.execute(select(Strategy).where(Strategy.id == sel.strategy_id))
        ).scalar_one_or_none()
    # default to built-in multi_tf_confluence
    return (
        await db.execute(
            select(Strategy)
            .where(Strategy.user_id.is_(None))
            .where(Strategy.slug == DEFAULT_BUILTIN_SLUG)
        )
    ).scalar_one_or_none()


async def _evaluate_for_user(r, db, user: User, symbol: str, tfs: list[str]) -> None:
    strategy = await _user_strategy_for(db, user, symbol)
    if strategy is None:
        return
    try:
        strat_def = load_yaml_text(strategy.code)
    except Exception as e:
        log.warning("strategy %s yaml invalid: %s", strategy.id, e)
        return

    cooldown_key = COOLDOWN_KEY_FMT.format(user_id=user.id, symbol=symbol, strategy_id=strategy.id)
    last_raw = await r.get(cooldown_key)
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw)
            if (datetime.now(timezone.utc) - last) < timedelta(minutes=strat_def.cooldown_min):
                return
        except Exception:
            pass

    needed_tfs = sorted(set(tfs) | set(strat_def.timeframes))
    tf_klines = {tf: await get_klines(r, symbol, tf) for tf in needed_tfs}
    blackout = await _calendar_blackout(r)
    news = await _recent_news(symbol)

    sig = evaluate(
        symbol,
        tf_klines,
        strategy=strat_def,
        news=news,
        blackout=blackout,
    )
    if sig is None:
        return

    row = SignalModel(
        user_id=user.id,
        strategy_id=strategy.id,
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
        **sig.model_dump(mode="json"),
    }
    await publish_signal(r, payload)
    await r.set(cooldown_key, datetime.now(timezone.utc).isoformat(), ex=strat_def.cooldown_min * 60)
    log.info(
        "signal user=%s symbol=%s strategy=%s side=%s conf=%.1f",
        user.id,
        symbol,
        strategy.slug,
        sig.side,
        sig.confidence,
    )


async def _evaluate_symbol(r, symbol: str, tfs: list[str]) -> None:
    async with SessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        for user in users:
            try:
                await _evaluate_for_user(r, db, user, symbol, tfs)
            except Exception as e:
                log.warning("evaluate user=%s symbol=%s failed: %s", user.id, symbol, e)


async def main() -> None:
    s = get_settings()
    r = make_redis()
    pubsub = await subscribe(r, [SIGNAL_CHANNEL])
    log.info("signals worker subscribed; tracking %s on %s", s.symbols, s.timeframes)
    async for msg in pubsub.listen():
        if msg.get("type") != "message":
            continue
        try:
            data = json.loads(msg["data"])
        except Exception:
            continue
        if data.get("event") != "kline_closed":
            continue
        symbol = data.get("symbol")
        if symbol not in s.symbols:
            continue
        try:
            await _evaluate_symbol(r, symbol, s.timeframes)
        except Exception as e:
            log.warning("evaluate %s failed: %s", symbol, e)


if __name__ == "__main__":
    asyncio.run(main())
