from __future__ import annotations

from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.brokers.factory import get_broker_for_user
from app.db.models import Order, RiskConfig, ScenarioRun, User
from app.db.session import get_db
from app.keys.store import list_keyed_exchanges
from app.scenario.simulator import preset_shocks, simulate

router = APIRouter(prefix="/risk", tags=["risk"])


class ScenarioIn(BaseModel):
    preset: str = "gap_down"
    magnitude_pct: float = Field(default=5.0, ge=0, le=100)
    price_shocks: dict[str, float] | None = None


async def _live_positions(user: User, db: AsyncSession) -> list[dict]:
    rows: list[dict] = []
    for exchange in await list_keyed_exchanges(db, user.id):
        broker = await get_broker_for_user(db, user.id, exchange)
        if broker is None:
            continue
        try:
            for p in await broker.positions():
                p = dict(p)
                p["exchange"] = exchange
                rows.append(p)
        finally:
            await broker.close()
    return rows


@router.post("/scenarios")
async def run_scenario(
    body: ScenarioIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = (
        await db.execute(select(RiskConfig).where(RiskConfig.user_id == user.id))
    ).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(400, "risk config missing")
    today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    realized = (
        await db.execute(
            select(func.coalesce(func.sum(Order.realized_pnl_usdt), 0.0))
            .where(Order.user_id == user.id)
            .where(Order.closed_at >= today_start)
        )
    ).scalar_one()
    shocks = body.price_shocks if body.price_shocks is not None else preset_shocks(body.preset, body.magnitude_pct)
    result = simulate(
        await _live_positions(user, db),
        price_shocks=shocks,
        daily_realized_pnl_usdt=float(realized),
        daily_loss_limit_usdt=cfg.daily_loss_limit_usdt,
    )
    result["preset"] = body.preset
    result["price_shocks"] = shocks
    row = ScenarioRun(user_id=user.id, status="completed", input=body.model_dump(), result=result)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"run_id": row.id, **result}


@router.get("/scenarios/{run_id}")
async def get_scenario(
    run_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(select(ScenarioRun).where(ScenarioRun.id == run_id, ScenarioRun.user_id == user.id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "scenario run not found")
    return {"run_id": row.id, **row.result}
