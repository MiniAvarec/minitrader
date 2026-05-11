"""Trading journal endpoints.

The journal is a read-and-annotate view over `orders`. All endpoints are
per-user (filtered via `Order.user_id == current_user.id`). Aggregates and
the equity curve are computed in Python over the filtered set — these
datasets are bounded (typical user has <100k closed deals).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth.deps import current_user
from app.db.models import Order, Signal, SignalSide, Strategy, User
from app.db.session import get_db


router = APIRouter(prefix="/journal", tags=["journal"])


# ---------- filter parsing ----------


SortField = Literal["created_at", "closed_at", "pnl", "roi", "duration"]
SortOrder = Literal["asc", "desc"]
OutcomeFilter = Literal["all", "win", "loss", "breakeven"]
StatusFilter = Literal["all", "open", "closed", "partial"]


class DealFilters:
    """Bundles the common query params. Used by every endpoint here."""

    def __init__(
        self,
        date_from: datetime | None = Query(None),
        date_to: datetime | None = Query(None),
        symbols: list[str] | None = Query(None),
        exchange: str | None = Query(None),
        side: Literal["buy", "sell"] | None = Query(None),
        status: StatusFilter = Query("all"),
        strategy_id: int | None = Query(None),
        outcome: OutcomeFilter = Query("all"),
        min_pnl: float | None = Query(None),
        max_pnl: float | None = Query(None),
        search: str | None = Query(None),
    ):
        self.date_from = date_from
        self.date_to = date_to
        self.symbols = [s for s in (symbols or []) if s]
        self.exchange = exchange
        self.side = side
        self.status = status
        self.strategy_id = strategy_id
        self.outcome = outcome
        self.min_pnl = min_pnl
        self.max_pnl = max_pnl
        self.search = (search or "").strip() or None

    def apply(self, stmt, *, user_id: int):
        stmt = stmt.where(Order.user_id == user_id)
        if self.date_from:
            stmt = stmt.where(Order.created_at >= self.date_from)
        if self.date_to:
            stmt = stmt.where(Order.created_at <= self.date_to)
        if self.symbols:
            stmt = stmt.where(Order.symbol.in_(self.symbols))
        if self.exchange:
            stmt = stmt.where(Order.exchange == self.exchange)
        if self.side:
            stmt = stmt.where(
                Order.side == (SignalSide.buy if self.side == "buy" else SignalSide.sell)
            )
        if self.status != "all":
            stmt = stmt.where(Order.status == self.status)
        if self.min_pnl is not None:
            stmt = stmt.where(Order.realized_pnl_usdt >= self.min_pnl)
        if self.max_pnl is not None:
            stmt = stmt.where(Order.realized_pnl_usdt <= self.max_pnl)
        if self.outcome == "win":
            stmt = stmt.where(Order.realized_pnl_usdt > 0)
        elif self.outcome == "loss":
            stmt = stmt.where(Order.realized_pnl_usdt < 0)
        elif self.outcome == "breakeven":
            stmt = stmt.where(Order.realized_pnl_usdt == 0)
        if self.search:
            needle = f"%{self.search}%"
            stmt = stmt.where(or_(Order.symbol.ilike(needle), Order.notes.ilike(needle)))
        # strategy_id is on Signal, so we filter via join later
        return stmt


def _row_to_deal(o: Order, strategy_name: str | None) -> dict:
    """Serialize an Order with derived fields the UI needs."""
    duration_s: int | None = None
    if o.closed_at and o.created_at:
        duration_s = max(0, int((o.closed_at - o.created_at).total_seconds()))
    roi_pct: float | None = None
    if o.notional_usdt:
        roi_pct = float(o.realized_pnl_usdt) / float(o.notional_usdt) * 100.0
    r_multiple: float | None = None
    if o.sl and o.qty and o.entry_price:
        risk_per_unit = abs(o.entry_price - o.sl)
        risk_usdt = risk_per_unit * o.qty
        if risk_usdt > 0:
            r_multiple = float(o.realized_pnl_usdt) / risk_usdt
    return {
        "id": o.id,
        "signal_id": o.signal_id,
        "exchange": o.exchange,
        "symbol": o.symbol,
        "side": o.side.value,
        "qty": o.qty,
        "notional_usdt": o.notional_usdt,
        "entry_price": o.entry_price,
        "exit_price": o.exit_price,
        "sl": o.sl,
        "tp": o.tp,
        "realized_pnl_usdt": o.realized_pnl_usdt,
        "fee_usdt": o.fee_usdt or 0.0,
        "roi_pct": roi_pct,
        "r_multiple": r_multiple,
        "duration_s": duration_s,
        "status": o.status,
        "created_at": o.created_at.isoformat(),
        "closed_at": o.closed_at.isoformat() if o.closed_at else None,
        "strategy_id": None,  # filled in by the caller after the join
        "strategy_name": strategy_name,
        "notes": o.notes,
        "tags": list(o.tags or []),
        "exchange_order_id": o.exchange_order_id,
    }


async def _load_deals(
    db: AsyncSession,
    user_id: int,
    f: DealFilters,
    *,
    limit: int | None,
    offset: int,
    sort: SortField,
    order: SortOrder,
) -> list[dict]:
    StrategyAlias = aliased(Strategy)
    SignalAlias = aliased(Signal)
    stmt = (
        select(Order, SignalAlias.strategy_id, StrategyAlias.name)
        .outerjoin(SignalAlias, SignalAlias.id == Order.signal_id)
        .outerjoin(StrategyAlias, StrategyAlias.id == SignalAlias.strategy_id)
    )
    stmt = f.apply(stmt, user_id=user_id)
    if f.strategy_id is not None:
        stmt = stmt.where(SignalAlias.strategy_id == f.strategy_id)

    direction = (lambda c: c.desc()) if order == "desc" else (lambda c: c.asc())
    if sort == "pnl":
        stmt = stmt.order_by(direction(Order.realized_pnl_usdt), Order.id.desc())
    elif sort == "closed_at":
        stmt = stmt.order_by(direction(Order.closed_at), Order.id.desc())
    elif sort == "roi" or sort == "duration":
        # Computed fields — sort in Python after fetch.
        stmt = stmt.order_by(Order.created_at.desc())
    else:
        stmt = stmt.order_by(direction(Order.created_at), Order.id.desc())

    rows = (await db.execute(stmt)).all()
    deals: list[dict] = []
    for order_row, strategy_id, strategy_name in rows:
        d = _row_to_deal(order_row, strategy_name)
        d["strategy_id"] = strategy_id
        deals.append(d)

    if sort == "roi":
        deals.sort(
            key=lambda d: (d["roi_pct"] is None, d["roi_pct"] or 0.0),
            reverse=(order == "desc"),
        )
    elif sort == "duration":
        deals.sort(
            key=lambda d: (d["duration_s"] is None, d["duration_s"] or 0),
            reverse=(order == "desc"),
        )

    if limit is not None:
        deals = deals[offset : offset + limit]
    return deals


# ---------- endpoints ----------


@router.get("/deals")
async def list_deals(
    f: DealFilters = Depends(),
    sort: SortField = Query("created_at"),
    order: SortOrder = Query("desc"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _load_deals(
        db, user.id, f, limit=limit, offset=offset, sort=sort, order=order
    )


@router.get("/stats")
async def journal_stats(
    f: DealFilters = Depends(),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    deals = await _load_deals(
        db, user.id, f, limit=None, offset=0, sort="created_at", order="asc"
    )

    open_deals = [d for d in deals if d["status"] != "closed"]
    closed = [d for d in deals if d["status"] == "closed"]
    wins = [d for d in closed if d["realized_pnl_usdt"] > 0]
    losses = [d for d in closed if d["realized_pnl_usdt"] < 0]
    breakeven = [d for d in closed if d["realized_pnl_usdt"] == 0]

    gross_profit = sum(d["realized_pnl_usdt"] for d in wins)
    gross_loss = sum(d["realized_pnl_usdt"] for d in losses)  # negative
    net_pnl = gross_profit + gross_loss
    win_rate = (len(wins) / len(closed)) if closed else 0.0
    profit_factor = (
        (gross_profit / abs(gross_loss)) if gross_loss < 0 else None
    )
    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
    largest_win = max((d["realized_pnl_usdt"] for d in wins), default=0.0)
    largest_loss = min((d["realized_pnl_usdt"] for d in losses), default=0.0)
    avg_duration_s = (
        sum((d["duration_s"] or 0) for d in closed) / len(closed) if closed else 0
    )

    # Equity curve drawdown — walk closed deals in chronological order.
    sorted_closed = sorted(
        closed, key=lambda d: d["closed_at"] or d["created_at"]
    )
    equity = 0.0
    peak = 0.0
    max_dd_usdt = 0.0
    starting_capital_proxy = 0.0
    for d in sorted_closed:
        equity += d["realized_pnl_usdt"]
        starting_capital_proxy = max(starting_capital_proxy, d["notional_usdt"])
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd_usdt:
            max_dd_usdt = dd
    # Express drawdown as % of the largest single notional we've seen — a
    # rough denominator since we don't track account-balance history.
    max_dd_pct = (
        (max_dd_usdt / starting_capital_proxy * 100.0)
        if starting_capital_proxy > 0
        else 0.0
    )

    def _agg(key_fn) -> dict:
        buckets: dict = defaultdict(lambda: {"count": 0, "wins": 0, "net_pnl": 0.0})
        for d in closed:
            k = key_fn(d)
            if k is None:
                continue
            b = buckets[k]
            b["count"] += 1
            b["net_pnl"] += d["realized_pnl_usdt"]
            if d["realized_pnl_usdt"] > 0:
                b["wins"] += 1
        out: dict[str, dict] = {}
        for k, b in buckets.items():
            out[str(k)] = {
                "count": b["count"],
                "net_pnl": round(b["net_pnl"], 6),
                "win_rate": (b["wins"] / b["count"]) if b["count"] else 0.0,
            }
        return out

    by_symbol = _agg(lambda d: d["symbol"])
    by_side = _agg(lambda d: d["side"])
    by_strategy = _agg(lambda d: d["strategy_name"] or "—")
    by_day_of_week = _agg(
        lambda d: datetime.fromisoformat(d["closed_at"]).weekday()
        if d["closed_at"]
        else None
    )
    by_hour_of_day = _agg(
        lambda d: datetime.fromisoformat(d["closed_at"]).hour
        if d["closed_at"]
        else None
    )

    return {
        "count": len(closed),
        "open": len(open_deals),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate": win_rate,
        "net_pnl": net_pnl,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "expectancy": expectancy,
        "avg_duration_s": avg_duration_s,
        "max_drawdown_usdt": max_dd_usdt,
        "max_drawdown_pct": max_dd_pct,
        "by_symbol": by_symbol,
        "by_side": by_side,
        "by_strategy": by_strategy,
        "by_day_of_week": by_day_of_week,
        "by_hour_of_day": by_hour_of_day,
    }


@router.get("/equity-curve")
async def equity_curve(
    f: DealFilters = Depends(),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    deals = await _load_deals(
        db, user.id, f, limit=None, offset=0, sort="created_at", order="asc"
    )
    closed = sorted(
        (d for d in deals if d["status"] == "closed" and d["closed_at"]),
        key=lambda d: d["closed_at"],
    )
    points = []
    equity = 0.0
    for d in closed:
        equity += d["realized_pnl_usdt"]
        points.append(
            {
                "t": d["closed_at"],
                "pnl": d["realized_pnl_usdt"],
                "equity": equity,
            }
        )
    return {"points": points}


@router.get("/filters")
async def filter_options(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    symbols = (
        await db.execute(
            select(Order.symbol)
            .where(Order.user_id == user.id)
            .group_by(Order.symbol)
            .order_by(Order.symbol)
        )
    ).scalars().all()
    exchanges = (
        await db.execute(
            select(Order.exchange)
            .where(Order.user_id == user.id)
            .group_by(Order.exchange)
            .order_by(Order.exchange)
        )
    ).scalars().all()
    strategy_rows = (
        await db.execute(
            select(Strategy.id, Strategy.name)
            .join(Signal, Signal.strategy_id == Strategy.id)
            .join(Order, Order.signal_id == Signal.id)
            .where(Order.user_id == user.id)
            .group_by(Strategy.id, Strategy.name)
            .order_by(Strategy.name)
        )
    ).all()
    return {
        "symbols": list(symbols),
        "exchanges": list(exchanges),
        "strategies": [{"id": sid, "name": name} for sid, name in strategy_rows],
    }


class AnnotationIn(BaseModel):
    notes: str | None = None
    tags: list[str] | None = None


@router.patch("/deals/{deal_id}")
async def update_deal_annotations(
    deal_id: int,
    body: AnnotationIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(Order).where(and_(Order.id == deal_id, Order.user_id == user.id))
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "deal not found")
    if body.notes is not None:
        row.notes = body.notes[:2048] or None
    if body.tags is not None:
        clean = [str(t).strip()[:48] for t in body.tags if str(t).strip()]
        # De-dupe while preserving order.
        seen: set[str] = set()
        deduped: list[str] = []
        for t in clean:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        row.tags = deduped[:32]
    await db.commit()
    await db.refresh(row)

    # Re-fetch strategy_name for the response.
    strategy_name = None
    strategy_id_value = None
    if row.signal_id:
        srow = (
            await db.execute(
                select(Strategy.id, Strategy.name)
                .join(Signal, Signal.strategy_id == Strategy.id)
                .where(Signal.id == row.signal_id)
            )
        ).first()
        if srow is not None:
            strategy_id_value, strategy_name = srow
    deal = _row_to_deal(row, strategy_name)
    deal["strategy_id"] = strategy_id_value
    return deal
