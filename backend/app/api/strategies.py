"""Strategy CRUD + selection + validate + backtest."""
from __future__ import annotations

from datetime import datetime, timezone
import re

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.config import get_settings
from app.db.models import Strategy, User, UserStrategySelection
from app.db.session import get_db
from app.signals.dsl.loader import StrategyParseError, load_yaml_text

router = APIRouter(prefix="/strategies", tags=["strategies"])


# ---------- response shapes ----------

class StrategyOut(BaseModel):
    id: int
    user_id: int | None
    parent_id: int | None
    slug: str
    name: str
    description: str
    code: str
    is_builtin: bool
    version: int
    created_at: str
    updated_at: str


class StrategyListItem(BaseModel):
    id: int
    slug: str
    name: str
    description: str
    is_builtin: bool
    is_mine: bool


class SelectionOut(BaseModel):
    symbol: str
    strategy_id: int
    enabled: bool


# ---------- helpers ----------

def _to_out(s: Strategy) -> StrategyOut:
    return StrategyOut(
        id=s.id,
        user_id=s.user_id,
        parent_id=s.parent_id,
        slug=s.slug,
        name=s.name,
        description=s.description or "",
        code=s.code,
        is_builtin=s.is_builtin,
        version=s.version,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "strategy"


async def _user_owned(db: AsyncSession, user: User, strategy_id: int) -> Strategy:
    s = (
        await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "strategy not found")
    if s.is_builtin or s.user_id != user.id:
        raise HTTPException(403, "you can only edit your own strategies")
    return s


# ---------- list / detail ----------

@router.get("", response_model=list[StrategyListItem])
async def list_strategies(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.execute(
            select(Strategy)
            .where(or_(Strategy.is_builtin.is_(True), Strategy.user_id == user.id))
            .order_by(Strategy.is_builtin.desc(), Strategy.name)
        )
    ).scalars().all()
    return [
        StrategyListItem(
            id=s.id,
            slug=s.slug,
            name=s.name,
            description=s.description or "",
            is_builtin=s.is_builtin,
            is_mine=s.user_id == user.id,
        )
        for s in rows
    ]


@router.get("/selections", response_model=list[SelectionOut])
async def list_selections(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.execute(
            select(UserStrategySelection).where(UserStrategySelection.user_id == user.id)
        )
    ).scalars().all()
    return [
        SelectionOut(symbol=r.symbol, strategy_id=r.strategy_id, enabled=r.enabled) for r in rows
    ]


class SelectionIn(BaseModel):
    symbol: str
    strategy_id: int
    enabled: bool = True


@router.put("/selections", response_model=SelectionOut)
async def upsert_selection(
    body: SelectionIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    s = (
        await db.execute(select(Strategy).where(Strategy.id == body.strategy_id))
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "strategy not found")
    if not (s.is_builtin or s.user_id == user.id):
        raise HTTPException(403, "cannot use someone else's strategy")
    sym = body.symbol.upper()
    if sym not in get_settings().symbols:
        raise HTTPException(400, f"symbol {sym!r} is not tracked")
    existing = (
        await db.execute(
            select(UserStrategySelection)
            .where(UserStrategySelection.user_id == user.id)
            .where(UserStrategySelection.symbol == sym)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = UserStrategySelection(
            user_id=user.id, symbol=sym, strategy_id=body.strategy_id, enabled=body.enabled
        )
        db.add(existing)
    else:
        existing.strategy_id = body.strategy_id
        existing.enabled = body.enabled
        existing.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return SelectionOut(symbol=sym, strategy_id=body.strategy_id, enabled=body.enabled)


@router.delete("/selections/{symbol}")
async def delete_selection(
    symbol: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    sel = (
        await db.execute(
            select(UserStrategySelection)
            .where(UserStrategySelection.user_id == user.id)
            .where(UserStrategySelection.symbol == symbol.upper())
        )
    ).scalar_one_or_none()
    if sel is not None:
        await db.delete(sel)
        await db.commit()
    return {"ok": True}


@router.get("/{strategy_id}", response_model=StrategyOut)
async def get_strategy(
    strategy_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    s = (
        await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "strategy not found")
    if not (s.is_builtin or s.user_id == user.id):
        raise HTTPException(403)
    return _to_out(s)


# ---------- mutate ----------

@router.post("/{strategy_id}/clone", response_model=StrategyOut)
async def clone_strategy(
    strategy_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    parent = (
        await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    ).scalar_one_or_none()
    if parent is None:
        raise HTTPException(404, "strategy not found")
    if not (parent.is_builtin or parent.user_id == user.id):
        raise HTTPException(403)
    base_slug = _slugify(parent.slug)
    slug = base_slug
    n = 2
    while True:
        exists = (
            await db.execute(
                select(Strategy)
                .where(Strategy.user_id == user.id)
                .where(Strategy.slug == slug)
            )
        ).scalar_one_or_none()
        if exists is None:
            break
        slug = f"{base_slug}_{n}"
        n += 1
    copy = Strategy(
        user_id=user.id,
        parent_id=parent.id,
        slug=slug,
        name=f"{parent.name} (copy)",
        description=parent.description,
        code=parent.code,
        is_builtin=False,
        version=1,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return _to_out(copy)


class StrategyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    code: str  # YAML text — required


@router.put("/{strategy_id}", response_model=StrategyOut)
async def update_strategy(
    strategy_id: int,
    body: StrategyUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    s = await _user_owned(db, user, strategy_id)
    try:
        parsed = load_yaml_text(body.code)
    except StrategyParseError as e:
        raise HTTPException(400, f"invalid YAML: {e}")
    s.code = body.code
    s.name = body.name or parsed.name or s.name
    s.description = body.description if body.description is not None else (parsed.description or s.description)
    s.version = (s.version or 1) + 1
    s.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(s)
    return _to_out(s)


@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    s = await _user_owned(db, user, strategy_id)
    await db.delete(s)
    await db.commit()
    return {"ok": True}


@router.post("/validate")
async def validate_yaml(
    body: dict = Body(...),
    user: User = Depends(current_user),
):
    code = body.get("code") or ""
    try:
        parsed = load_yaml_text(code)
    except StrategyParseError as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "name": parsed.name,
        "timeframes": parsed.timeframes,
        "params": parsed.params,
    }


class BacktestIn(BaseModel):
    symbol: str
    hours: int = 168
    notional_usdt: float = 100.0


@router.post("/{strategy_id}/backtest")
async def backtest_strategy(
    strategy_id: int,
    body: BacktestIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    s = (
        await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "strategy not found")
    if not (s.is_builtin or s.user_id == user.id):
        raise HTTPException(403)
    try:
        parsed = load_yaml_text(s.code)
    except StrategyParseError as e:
        raise HTTPException(400, f"strategy YAML invalid: {e}")
    sym = body.symbol.upper()
    if sym not in get_settings().symbols:
        raise HTTPException(400, f"symbol {sym!r} is not tracked")
    hours = max(6, min(body.hours, 720))

    from app.backtest.runner import run as bt_run

    result = await bt_run(parsed, sym, hours=hours, notional_usdt=body.notional_usdt)
    return {
        "symbol": result.symbol,
        "hours": result.hours,
        "win_rate": result.win_rate,
        "total_pnl_usdt": result.total_pnl_usdt,
        "total_pnl_pct": result.total_pnl_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "trades": [t.__dict__ for t in result.trades],
        "equity_curve": result.equity_curve,
    }
