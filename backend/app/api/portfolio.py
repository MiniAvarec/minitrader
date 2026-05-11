from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.brokers.base import from_ccxt_symbol
from app.brokers.factory import get_broker_for_user
from app.db.models import PortfolioRebalanceRun, TradingMode, User
from app.db.session import get_db
from app.keys.store import list_keyed_exchanges
from app.orders.executor import place_market_order
from app.portfolio.rebalancer import build_plan, normalize_position

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class RebalanceIn(BaseModel):
    max_exchange_share: float = Field(default=0.60, ge=0.05, le=1.0)
    max_asset_share: float = Field(default=0.50, ge=0.05, le=1.0)
    min_order_notional_usdt: float = Field(default=10.0, ge=0)


async def _positions(user: User, db: AsyncSession) -> list:
    out = []
    for exchange in await list_keyed_exchanges(db, user.id):
        broker = await get_broker_for_user(db, user.id, exchange)
        if broker is None:
            continue
        try:
            for raw in await broker.positions():
                pos = normalize_position(exchange, raw)
                if pos is not None:
                    out.append(pos)
        finally:
            await broker.close()
    return out


async def _preview(body: RebalanceIn, user: User, db: AsyncSession) -> dict:
    positions = await _positions(user, db)
    result = build_plan(
        positions,
        max_exchange_share=body.max_exchange_share,
        max_asset_share=body.max_asset_share,
        min_order_notional_usdt=body.min_order_notional_usdt,
    )
    result["can_execute"] = user.mode == TradingMode.auto_execute
    return result


@router.post("/rebalance/preview")
async def preview_rebalance(
    body: RebalanceIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await _preview(body, user, db)
    row = PortfolioRebalanceRun(user_id=user.id, status="preview", input=body.model_dump(), result=result)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"run_id": row.id, **result}


@router.post("/rebalance/execute")
async def execute_rebalance(
    body: RebalanceIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.mode != TradingMode.auto_execute:
        raise HTTPException(400, "auto_execute mode is required")
    result = await _preview(body, user, db)
    order_ids: list[int] = []
    executions = []
    for intent in result.get("intents", []):
        if not intent.get("reduce_only"):
            continue
        exchange = intent["exchange"]
        symbol = from_ccxt_symbol(exchange, intent["symbol"])
        ok, reason, order = await place_market_order(
            db=db,
            user=user,
            exchange=exchange,
            symbol=symbol,
            side=intent["side"],
            notional_usdt=float(intent["notional_usdt"]),
            reduce_only=True,
        )
        if order:
            order_ids.append(order.id)
        executions.append({"intent": intent, "ok": ok, "reason": reason, "order_id": order.id if order else None})
    result["executions"] = executions
    row = PortfolioRebalanceRun(
        user_id=user.id,
        status="executed",
        input=body.model_dump(),
        result=result,
        order_ids=order_ids,
        executed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()
    return {"run_id": row.id, **result}
