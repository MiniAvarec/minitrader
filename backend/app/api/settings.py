import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.db.models import RiskConfig, TradingMode, User
from app.db.session import get_db

router = APIRouter(prefix="/settings", tags=["settings"])


class RiskIn(BaseModel):
    max_notional_usdt: float
    daily_loss_limit_usdt: float
    max_concurrent_positions: int
    require_sl_tp: bool = True


class ModeIn(BaseModel):
    mode: str  # "signal_only" | "auto_execute"


class TelegramTokenOut(BaseModel):
    link_token: str


@router.get("/risk")
async def get_risk(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    cfg = (
        await db.execute(select(RiskConfig).where(RiskConfig.user_id == user.id))
    ).scalar_one_or_none()
    if cfg is None:
        cfg = RiskConfig(user_id=user.id)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return {
        "max_notional_usdt": cfg.max_notional_usdt,
        "daily_loss_limit_usdt": cfg.daily_loss_limit_usdt,
        "max_concurrent_positions": cfg.max_concurrent_positions,
        "require_sl_tp": cfg.require_sl_tp,
    }


@router.put("/risk")
async def put_risk(
    body: RiskIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = (
        await db.execute(select(RiskConfig).where(RiskConfig.user_id == user.id))
    ).scalar_one_or_none()
    if cfg is None:
        cfg = RiskConfig(user_id=user.id)
        db.add(cfg)
    cfg.max_notional_usdt = body.max_notional_usdt
    cfg.daily_loss_limit_usdt = body.daily_loss_limit_usdt
    cfg.max_concurrent_positions = body.max_concurrent_positions
    cfg.require_sl_tp = body.require_sl_tp
    await db.commit()
    return {"ok": True}


@router.put("/mode")
async def put_mode(
    body: ModeIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.mode not in {"signal_only", "auto_execute"}:
        raise HTTPException(400, "invalid mode")
    user.mode = TradingMode(body.mode)
    await db.commit()
    return {"ok": True, "mode": user.mode.value}


@router.post("/telegram/link", response_model=TelegramTokenOut)
async def telegram_link(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    token = secrets.token_urlsafe(16)
    user.telegram_link_token = token
    await db.commit()
    return TelegramTokenOut(link_token=token)


@router.delete("/telegram")
async def telegram_unlink(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    user.telegram_chat_id = None
    user.telegram_link_token = None
    await db.commit()
    return {"ok": True}
