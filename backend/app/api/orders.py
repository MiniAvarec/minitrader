from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.db.models import Order, Signal as SignalModel, SignalStatus, User
from app.db.session import get_db
from app.orders.executor import place_for_signal

router = APIRouter(prefix="/orders", tags=["orders"])


class ExecuteIn(BaseModel):
    signal_id: int
    notional_usdt: float | None = None


@router.get("")
async def list_orders(
    limit: int = 50,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Order)
            .where(Order.user_id == user.id)
            .order_by(Order.created_at.desc())
            .limit(min(limit, 200))
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "signal_id": r.signal_id,
            "exchange": r.exchange,
            "symbol": r.symbol,
            "side": r.side.value,
            "qty": r.qty,
            "notional_usdt": r.notional_usdt,
            "entry_price": r.entry_price,
            "sl": r.sl,
            "tp": r.tp,
            "status": r.status,
            "exchange_order_id": r.exchange_order_id,
            "created_at": r.created_at.isoformat(),
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
            "realized_pnl_usdt": r.realized_pnl_usdt,
        }
        for r in rows
    ]


@router.post("/execute")
async def execute_signal(
    body: ExecuteIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    sig = (
        await db.execute(select(SignalModel).where(SignalModel.id == body.signal_id))
    ).scalar_one_or_none()
    if sig is None:
        raise HTTPException(404, "signal not found")
    ok, reason, order = await place_for_signal(
        db=db, user=user, signal=sig, notional_usdt=body.notional_usdt
    )
    if ok:
        sig.status = SignalStatus.executed
        await db.commit()
        return {"ok": True, "order_id": order.id, "exchange_order_id": order.exchange_order_id}
    return {"ok": False, "reason": reason}
