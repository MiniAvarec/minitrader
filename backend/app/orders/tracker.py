"""Position tracker.

Periodically (every 30s) reconciles open Order rows against Binance positions:
- If a row's symbol no longer has an open position on the user's account,
  we mark it `closed` and pull the realized PnL from Binance income history.
- This is what makes the daily-loss kill-switch in app/risk/checks.py real.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import Broker, to_ccxt_symbol
from app.brokers.factory import get_broker_for_user
from app.data.redis_io import make_redis
from app.db.models import ApiKey, Order, User
from app.db.session import SessionLocal

log = logging.getLogger("tracker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

POLL_INTERVAL_S = 30
FILLSTREAM_HEARTBEAT_FRESH_S = 60


async def _fillstream_alive(r, user_id: int, exchange: str) -> bool:
    try:
        ts = await r.get(f"fillstream:hb:{user_id}:{exchange}")
        if not ts:
            return False
        return (datetime.now(timezone.utc).timestamp() - float(ts)) < FILLSTREAM_HEARTBEAT_FRESH_S
    except Exception:
        return False


async def _close_orphans(
    db: AsyncSession, user: User, exchange: str, broker: Broker, *, fill_alive: bool
) -> None:
    open_orders = (
        await db.execute(
            select(Order)
            .where(Order.user_id == user.id)
            .where(Order.exchange == exchange)
            .where(Order.status == "open")
        )
    ).scalars().all()
    if not open_orders:
        return
    positions = await broker.positions()
    open_syms = {p["symbol"] for p in positions}
    for order in open_orders:
        ccxt_sym = to_ccxt_symbol(exchange, order.symbol)
        if ccxt_sym in open_syms:
            continue
        if fill_alive:
            # The user-data WS was supposed to detect this. Log a gap warning so
            # we notice that primary failed and backup is doing real work.
            log.warning(
                "tracker.gap_found user=%s exchange=%s order=%s — fillstream missed it",
                user.id, exchange, order.id,
            )
        try:
            since_ms = int(order.created_at.timestamp() * 1000)
            pnl = await broker.fetch_realized_pnl(order.symbol, since_ms)
        except Exception as e:
            log.warning("realized PnL pull failed for order %s: %s", order.id, e)
            pnl = 0.0
        order.realized_pnl_usdt = pnl
        if order.exit_price is None and order.qty > 0:
            # Approximate exit_price from net PnL — close-fill avg_price was never
            # observed by this code path. Fees fold into realized_pnl, so this is
            # the price that reconciles to what the user sees on the exchange.
            direction = 1.0 if order.side.value == "buy" else -1.0
            order.exit_price = order.entry_price + direction * pnl / order.qty
        order.status = "closed"
        order.closed_at = datetime.now(timezone.utc)
        log.info("closed order %s pnl=%.2f", order.id, pnl)
    await db.commit()


async def main() -> None:
    r = make_redis()
    while True:
        try:
            async with SessionLocal() as db:
                rows = (
                    await db.execute(
                        select(ApiKey.user_id, ApiKey.exchange).where(
                            ApiKey.label == "default"
                        )
                    )
                ).all()
                for user_id, exchange in rows:
                    user = (
                        await db.execute(select(User).where(User.id == user_id))
                    ).scalar_one_or_none()
                    if user is None:
                        continue
                    broker = await get_broker_for_user(db, user.id, exchange)
                    if broker is None:
                        continue
                    fill_alive = await _fillstream_alive(r, user.id, exchange)
                    try:
                        await _close_orphans(db, user, exchange, broker, fill_alive=fill_alive)
                    except Exception as e:
                        log.warning(
                            "user %s exchange %s tracker error: %s", user.id, exchange, e
                        )
                    finally:
                        await broker.close()
        except Exception as e:
            log.warning("tracker loop error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    asyncio.run(main())
