"""Periodic refresh of cached exchangeInfo into the `instruments` table.

Subscribes to `instruments:refresh:<exchange>` for on-demand refresh, plus
runs all enabled exchanges every 6 hours.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.brokers.factory import SUPPORTED, get_broker
from app.config import get_settings
from app.data.redis_io import (
    INSTRUMENTS_REFRESH_CHANNEL_PREFIX,
    make_redis,
    subscribe,
)
from app.db.models import Instrument
from app.db.session import SessionLocal


log = logging.getLogger("instruments_refresh")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)

REFRESH_INTERVAL_S = 6 * 3600


async def refresh(exchange: str) -> int:
    """Pull exchangeInfo for `exchange` and upsert into `instruments`.

    Vanished symbols (in DB but not in latest fetch) are marked active=false.
    Returns the count of rows touched.
    """
    if exchange not in SUPPORTED:
        log.warning("skip unsupported exchange: %s", exchange)
        return 0
    s = get_settings()
    # Public REST works without keys for all three venues.
    broker = get_broker(exchange, "", "", testnet=s.testnet_for(exchange))
    try:
        infos = await broker.load_exchange_info()
    finally:
        await broker.close()

    if not infos:
        log.warning("%s exchangeInfo empty; aborting refresh", exchange)
        return 0

    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        seen: set[str] = set()
        for info in infos:
            seen.add(info.symbol)
            stmt = pg_insert(Instrument).values(
                exchange=info.exchange,
                symbol=info.symbol,
                base=info.base,
                quote=info.quote,
                contract_type=info.contract_type,
                tick_size=info.tick_size,
                lot_size=info.lot_size,
                min_qty=info.min_qty,
                min_notional=info.min_notional,
                ccxt_symbol=info.ccxt_symbol,
                active=info.active,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["exchange", "symbol"],
                set_={
                    "base": info.base,
                    "quote": info.quote,
                    "contract_type": info.contract_type,
                    "tick_size": info.tick_size,
                    "lot_size": info.lot_size,
                    "min_qty": info.min_qty,
                    "min_notional": info.min_notional,
                    "ccxt_symbol": info.ccxt_symbol,
                    "active": info.active,
                    "updated_at": now,
                },
            )
            await db.execute(stmt)
        # Mark anything not in `seen` as inactive.
        existing = (
            await db.execute(
                select(Instrument.symbol).where(Instrument.exchange == exchange)
            )
        ).scalars().all()
        vanished = [sym for sym in existing if sym not in seen]
        if vanished:
            await db.execute(
                update(Instrument)
                .where(Instrument.exchange == exchange)
                .where(Instrument.symbol.in_(vanished))
                .values(active=False, updated_at=now)
            )
        await db.commit()
    log.info("refreshed %s: %d instruments (deactivated %d)", exchange, len(infos), len(vanished))
    return len(infos)


async def _periodic_refresh() -> None:
    while True:
        s = get_settings()
        for ex in s.enabled_exchanges:
            try:
                await refresh(ex)
            except Exception as e:
                log.warning("%s refresh failed: %s", ex, e)
        await asyncio.sleep(REFRESH_INTERVAL_S)


async def _on_demand_listener() -> None:
    r = make_redis()
    pubsub = r.pubsub()
    channels = [
        f"{INSTRUMENTS_REFRESH_CHANNEL_PREFIX}{ex}"
        for ex in get_settings().enabled_exchanges
    ]
    await pubsub.psubscribe(f"{INSTRUMENTS_REFRESH_CHANNEL_PREFIX}*")
    log.info("listening for on-demand refresh on %s", channels)
    async for msg in pubsub.listen():
        if msg.get("type") not in {"pmessage", "message"}:
            continue
        channel = msg.get("channel", "")
        if not channel.startswith(INSTRUMENTS_REFRESH_CHANNEL_PREFIX):
            continue
        ex = channel.removeprefix(INSTRUMENTS_REFRESH_CHANNEL_PREFIX)
        try:
            await refresh(ex)
        except Exception as e:
            log.warning("on-demand refresh %s failed: %s", ex, e)


async def main() -> None:
    await asyncio.gather(_periodic_refresh(), _on_demand_listener())


if __name__ == "__main__":
    asyncio.run(main())
