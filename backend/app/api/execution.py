from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.brokers.factory import SUPPORTED, get_broker_for_user
from app.db.models import ExecutionRouteQuote, Instrument, TradingMode, User
from app.db.session import get_db
from app.execution.router import score_order_book
from app.keys.store import list_keyed_exchanges
from app.orders.executor import place_market_order

router = APIRouter(prefix="/execution", tags=["execution"])


class RouteIn(BaseModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell)$")
    notional_usdt: float = Field(gt=0)
    exchanges: list[str] | None = None
    sl: float | None = None
    tp: float | None = None


async def _instrument_for(db: AsyncSession, exchange: str, symbol: str) -> Instrument | None:
    # Case-insensitive: MT5/Exness symbols carry a lowercase suffix (BTCUSDm).
    exact = (
        await db.execute(
            select(Instrument).where(
                Instrument.exchange == exchange,
                func.upper(Instrument.symbol) == symbol.upper(),
            )
        )
    ).scalar_one_or_none()
    if exact:
        return exact
    # USDT base/quote fallback is crypto-only; harmless for Exness.
    sym = symbol.upper()
    base = sym[:-4] if sym.endswith("USDT") else sym.split("-")[0]
    return (
        await db.execute(
            select(Instrument)
            .where(Instrument.exchange == exchange)
            .where(Instrument.base == base)
            .where(Instrument.quote == "USDT")
            .where(Instrument.active.is_(True))
        )
    ).scalar_one_or_none()


async def _quote(body: RouteIn, user: User, db: AsyncSession) -> dict:
    keyed = set(await list_keyed_exchanges(db, user.id))
    requested = [e.lower() for e in (body.exchanges or list(SUPPORTED))]
    exchanges = [e for e in requested if e in keyed and e in SUPPORTED]
    candidates = []
    for exchange in exchanges:
        instrument = await _instrument_for(db, exchange, body.symbol)
        if instrument is None:
            candidates.append({"exchange": exchange, "symbol": body.symbol, "ok": False, "reason": "symbol unavailable"})
            continue
        broker = await get_broker_for_user(db, user.id, exchange)
        if broker is None:
            candidates.append({"exchange": exchange, "symbol": instrument.symbol, "ok": False, "reason": "missing API key"})
            continue
        try:
            book = await broker.order_book(instrument.ccxt_symbol, limit=20)
            candidate = score_order_book(
                exchange=exchange,
                symbol=instrument.symbol,
                order_book=book,
                side=body.side,
                notional_usdt=body.notional_usdt,
            )
            candidates.append(candidate.__dict__)
        finally:
            await broker.close()
    valid = [c for c in candidates if c.get("ok") and c.get("total_cost_usdt") is not None]
    best_row = min(valid, key=lambda c: c["total_cost_usdt"]) if valid else None
    return {"request": body.model_dump(), "candidates": candidates, "best": best_row, "can_execute": user.mode == TradingMode.auto_execute}


@router.post("/route")
async def route_order(
    body: RouteIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await _quote(body, user, db)
    row = ExecutionRouteQuote(user_id=user.id, status="quoted", input=body.model_dump(), result=result)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"run_id": row.id, **result}


@router.post("/route/execute")
async def execute_routed_order(
    body: RouteIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.mode != TradingMode.auto_execute:
        raise HTTPException(400, "auto_execute mode is required")
    result = await _quote(body, user, db)
    best = result.get("best")
    if not best:
        raise HTTPException(400, "no executable route")
    ok, reason, order = await place_market_order(
        db=db,
        user=user,
        exchange=best["exchange"],
        symbol=best["symbol"],
        side=body.side,
        notional_usdt=body.notional_usdt,
        sl=body.sl,
        tp=body.tp,
    )
    result["execution"] = {"ok": ok, "reason": reason, "order_id": order.id if order else None}
    row = ExecutionRouteQuote(
        user_id=user.id,
        status="executed" if ok else "failed",
        input=body.model_dump(),
        result=result,
        order_id=order.id if order else None,
        executed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()
    if not ok:
        return {"run_id": row.id, **result}
    return {"run_id": row.id, **result}
