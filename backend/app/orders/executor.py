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

from app.brokers.base import to_ccxt_symbol
from app.brokers.factory import get_broker_for_user
from app.data.redis_io import SIGNAL_CHANNEL, make_redis, subscribe
from app.db.models import (
    Instrument,
    Order,
    RiskConfig,
    Signal as SignalModel,
    SignalSide,
    TradingMode,
    User,
)
from app.db.session import SessionLocal
from app.orders.rounding import round_qty, round_price
from app.risk.checks import check_market_hours, evaluate_all

log = logging.getLogger("executor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


async def place_for_signal(
    *,
    db: AsyncSession,
    user: User,
    signal: SignalModel,
    notional_usdt: Optional[float] = None,
    exchange_override: str | None = None,
) -> tuple[bool, str, Order | None]:
    return await place_market_order(
        db=db,
        user=user,
        exchange=exchange_override or signal.exchange or "binance",
        symbol=signal.symbol,
        side=signal.side.value,
        notional_usdt=notional_usdt,
        sl=signal.sl,
        tp=signal.tp,
        signal_id=signal.id,
    )


async def place_market_order(
    *,
    db: AsyncSession,
    user: User,
    exchange: str,
    symbol: str,
    side: str,
    notional_usdt: Optional[float] = None,
    sl: float | None = None,
    tp: float | None = None,
    signal_id: int | None = None,
    reduce_only: bool = False,
) -> tuple[bool, str, Order | None]:
    cfg = (
        await db.execute(select(RiskConfig).where(RiskConfig.user_id == user.id))
    ).scalar_one_or_none()
    if cfg is None:
        return False, "risk config missing", None
    notional = notional_usdt or cfg.max_notional_usdt
    broker = await get_broker_for_user(db, user.id, exchange)
    if broker is None:
        return False, f"no {exchange} API key on file", None
    try:
        positions = await broker.positions()
        if not reduce_only:
            ok, results = await evaluate_all(
                db,
                user,
                notional_usdt=notional,
                sl=sl,
                tp=tp,
                open_positions=len(positions),
                signal_id=signal_id,
            )
            if not ok:
                failed = next((c for c in results if not c.ok), None)
                return False, f"risk: {failed.name}: {failed.reason}", None

        instrument = (
            await db.execute(
                select(Instrument).where(
                    Instrument.exchange == exchange, Instrument.symbol == symbol
                )
            )
        ).scalar_one_or_none()
        ccxt_sym = instrument.ccxt_symbol if instrument else to_ccxt_symbol(exchange, symbol)
        # IBKR has no ccxt analogue — pass the native dot-encoded symbol through.
        if exchange == "ibkr":
            ccxt_sym = symbol
            mh = await check_market_hours(
                broker,
                symbol,
                instrument.contract_type if instrument else "stock",
            )
            if not mh.ok:
                return False, f"risk: {mh.name}: {mh.reason}", None
        mark = await broker.mark_price(ccxt_sym)
        if mark <= 0:
            return False, "could not fetch mark price", None
        raw_qty = notional / mark
        qty = round_qty(raw_qty, instrument) if instrument else round(raw_qty, 4)
        if instrument and qty * mark < instrument.min_notional:
            return False, (
                f"qty*mark {qty * mark:.2f} below min_notional {instrument.min_notional}"
            ), None
        if instrument and instrument.min_qty and qty < instrument.min_qty:
            return False, f"qty {qty} below min_qty {instrument.min_qty}", None
        sl_price = round_price(sl, instrument) if (sl and instrument) else sl
        tp_price = round_price(tp, instrument) if (tp and instrument) else tp
        side_norm = "buy" if side == "buy" else "sell"
        order = await broker.place_market(
            ccxt_sym, side_norm, qty, sl=sl_price, tp=tp_price, reduce_only=reduce_only
        )
        row = Order(
            user_id=user.id,
            signal_id=signal_id,
            exchange=exchange,
            symbol=symbol,
            side=SignalSide.buy if side_norm == "buy" else SignalSide.sell,
            qty=qty,
            notional_usdt=notional,
            quote_currency=(instrument.currency if instrument else "USDT"),
            entry_price=mark,
            sl=sl_price,
            tp=tp_price,
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
