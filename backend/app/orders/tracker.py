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

from app.brokers.binance import BinanceBroker
from app.db.models import Order, User
from app.db.session import SessionLocal
from app.keys.store import load_key

log = logging.getLogger("tracker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

POLL_INTERVAL_S = 30


def _ccxt_symbol(symbol: str) -> str:
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}/USDT:USDT"
    return symbol


async def _close_orphans(db: AsyncSession, user: User, broker: BinanceBroker) -> None:
    open_orders = (
        await db.execute(
            select(Order).where(Order.user_id == user.id).where(Order.status == "open")
        )
    ).scalars().all()
    if not open_orders:
        return
    positions = await broker.positions()
    open_syms = {p["symbol"] for p in positions}
    for order in open_orders:
        ccxt_sym = _ccxt_symbol(order.symbol)
        if ccxt_sym in open_syms:
            continue
        # Position no longer open — pull realized PnL since order creation.
        try:
            since_ms = int(order.created_at.timestamp() * 1000)
            income = await broker.client.fapiprivate_get_income(
                {"symbol": order.symbol, "incomeType": "REALIZED_PNL", "startTime": since_ms}
            )
            pnl = sum(float(r.get("income", 0.0)) for r in income or [])
        except Exception as e:
            log.warning("income pull failed for order %s: %s", order.id, e)
            pnl = 0.0
        order.realized_pnl_usdt = pnl
        order.status = "closed"
        order.closed_at = datetime.now(timezone.utc)
        log.info("closed order %s pnl=%.2f", order.id, pnl)
    await db.commit()


async def main() -> None:
    while True:
        try:
            async with SessionLocal() as db:
                users = (await db.execute(select(User))).scalars().all()
                for user in users:
                    loaded = await load_key(db, user.id, "binance")
                    if loaded is None:
                        continue
                    api_key, api_secret, testnet = loaded
                    broker = BinanceBroker(api_key, api_secret, testnet=testnet)
                    try:
                        await _close_orphans(db, user, broker)
                    except Exception as e:
                        log.warning("user %s tracker error: %s", user.id, e)
                    finally:
                        await broker.close()
        except Exception as e:
            log.warning("tracker loop error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    asyncio.run(main())
