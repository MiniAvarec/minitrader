"""Order executor.

Two entry points:

1. Subscribed to the `signals` redis channel — for each signal it iterates over
   users in `auto_execute` mode and tries to place an order subject to risk
   checks. (Per-user position size is set to risk_config.max_notional_usdt
   for v1 simplicity.)

2. Public `place_for_signal(signal_id, user_id, notional_usdt?)` — used by
   the API and Telegram callbacks for manual execution.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.binance import BinanceBroker
from app.config import get_settings
from app.data.redis_io import SIGNAL_CHANNEL, make_redis, subscribe
from app.db.models import Order, RiskConfig, Signal as SignalModel, SignalSide, TradingMode, User
from app.db.session import SessionLocal
from app.keys.store import load_key
from app.risk.checks import evaluate_all

log = logging.getLogger("executor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


async def _broker_for(db: AsyncSession, user: User) -> BinanceBroker | None:
    loaded = await load_key(db, user.id, "binance")
    if not loaded:
        return None
    api_key, api_secret, testnet = loaded
    return BinanceBroker(api_key, api_secret, testnet=testnet)


def _ccxt_symbol(symbol: str) -> str:
    """Convert BTCUSDT -> BTC/USDT:USDT for ccxt USDT-M futures."""
    if symbol.endswith("USDT"):
        base = symbol[:-4]
        return f"{base}/USDT:USDT"
    return symbol


async def place_for_signal(
    *,
    db: AsyncSession,
    user: User,
    signal: SignalModel,
    notional_usdt: Optional[float] = None,
) -> tuple[bool, str, Order | None]:
    cfg = (
        await db.execute(select(RiskConfig).where(RiskConfig.user_id == user.id))
    ).scalar_one_or_none()
    if cfg is None:
        return False, "risk config missing", None
    notional = notional_usdt or cfg.max_notional_usdt
    broker = await _broker_for(db, user)
    if broker is None:
        return False, "no Binance API key on file", None
    try:
        positions = await broker.positions()
        ok, results = await evaluate_all(
            db,
            user,
            notional_usdt=notional,
            sl=signal.sl,
            tp=signal.tp,
            open_positions=len(positions),
            signal_id=signal.id,
        )
        if not ok:
            failed = next((c for c in results if not c.ok), None)
            return False, f"risk: {failed.name}: {failed.reason}", None

        ccxt_sym = _ccxt_symbol(signal.symbol)
        mark = await broker.mark_price(ccxt_sym)
        if mark <= 0:
            return False, "could not fetch mark price", None
        qty = round(notional / mark, 4)
        side = "buy" if signal.side == SignalSide.buy else "sell"
        order = await broker.place_market(
            ccxt_sym, side, qty, sl=signal.sl, tp=signal.tp
        )
        row = Order(
            user_id=user.id,
            signal_id=signal.id,
            symbol=signal.symbol,
            side=signal.side,
            qty=qty,
            notional_usdt=notional,
            entry_price=mark,
            sl=signal.sl,
            tp=signal.tp,
            exchange_order_id=str(order.get("id") or ""),
            status="open",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return True, "ok", row
    finally:
        await broker.close()


async def _on_signal(payload: dict) -> None:
    sig_id = payload.get("id")
    user_id = payload.get("user_id")
    if sig_id is None or user_id is None:
        return
    async with SessionLocal() as db:
        signal = (
            await db.execute(select(SignalModel).where(SignalModel.id == sig_id))
        ).scalar_one_or_none()
        if signal is None:
            return
        user = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None or user.mode != TradingMode.auto_execute:
            return
        try:
            ok, reason, _ = await place_for_signal(db=db, user=user, signal=signal)
            log.info("auto-exec user=%s sig=%s ok=%s reason=%s", user.id, sig_id, ok, reason)
        except Exception as e:
            log.warning("auto-exec failed user=%s: %s", user.id, e)


async def main() -> None:
    r = make_redis()
    pubsub = await subscribe(r, [SIGNAL_CHANNEL])
    log.info("executor subscribed")
    async for msg in pubsub.listen():
        if msg.get("type") != "message":
            continue
        try:
            data = json.loads(msg["data"])
        except Exception:
            continue
        if data.get("event") != "signal":
            continue
        try:
            await _on_signal(data)
        except Exception as e:
            log.warning("on_signal error: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
