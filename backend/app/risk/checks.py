"""Risk gates evaluated before any auto-execute order is placed."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Order, RiskConfig, RiskEvent, TradingMode, User


@dataclass
class CheckResult:
    name: str
    ok: bool
    reason: str


async def _get_config(db: AsyncSession, user: User) -> RiskConfig:
    cfg = (
        await db.execute(select(RiskConfig).where(RiskConfig.user_id == user.id))
    ).scalar_one_or_none()
    if cfg is None:
        cfg = RiskConfig(user_id=user.id)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


def check_size(notional_usdt: float, cfg: RiskConfig) -> CheckResult:
    if notional_usdt > cfg.max_notional_usdt:
        return CheckResult(
            "size_cap",
            False,
            f"notional ${notional_usdt:.2f} > cap ${cfg.max_notional_usdt:.2f}",
        )
    return CheckResult("size_cap", True, "ok")


def check_sl_tp(sl: float | None, tp: float | None, cfg: RiskConfig) -> CheckResult:
    if cfg.require_sl_tp and (sl is None or tp is None):
        return CheckResult("sl_tp_required", False, "missing SL or TP")
    return CheckResult("sl_tp_required", True, "ok")


async def check_daily_loss(db: AsyncSession, user: User, cfg: RiskConfig) -> CheckResult:
    today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    realized = (
        await db.execute(
            select(func.coalesce(func.sum(Order.realized_pnl_usdt), 0.0))
            .where(Order.user_id == user.id)
            .where(Order.closed_at >= today_start)
        )
    ).scalar_one()
    if float(realized) <= -float(cfg.daily_loss_limit_usdt):
        return CheckResult(
            "daily_loss",
            False,
            f"daily realized PnL ${float(realized):.2f} <= -${cfg.daily_loss_limit_usdt:.2f}",
        )
    return CheckResult("daily_loss", True, f"daily PnL ${float(realized):.2f}")


async def check_max_concurrent(open_positions: int, cfg: RiskConfig) -> CheckResult:
    if open_positions >= cfg.max_concurrent_positions:
        return CheckResult(
            "max_concurrent",
            False,
            f"{open_positions} open >= cap {cfg.max_concurrent_positions}",
        )
    return CheckResult("max_concurrent", True, "ok")


async def evaluate_all(
    db: AsyncSession,
    user: User,
    *,
    notional_usdt: float,
    sl: float | None,
    tp: float | None,
    open_positions: int,
    signal_id: int | None = None,
) -> tuple[bool, list[CheckResult]]:
    cfg = await _get_config(db, user)
    results = [
        check_size(notional_usdt, cfg),
        check_sl_tp(sl, tp, cfg),
        await check_daily_loss(db, user, cfg),
        await check_max_concurrent(open_positions, cfg),
    ]
    for c in results:
        db.add(
            RiskEvent(
                user_id=user.id,
                signal_id=signal_id,
                check_name=c.name,
                ok=c.ok,
                reason=c.reason,
            )
        )
    await db.commit()
    ok = all(c.ok for c in results)
    if not ok:
        # Auto-flip to signal-only if it was the daily-loss kill-switch
        for c in results:
            if c.name == "daily_loss" and not c.ok and user.mode == TradingMode.auto_execute:
                user.mode = TradingMode.signal_only
                await db.commit()
                break
    return ok, results
