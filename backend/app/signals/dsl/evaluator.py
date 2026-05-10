"""Evaluate a parsed StrategyDef against a MarketCtx → Signal | None."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.signals.dsl.market_ctx import MarketCtx
from app.signals.dsl.schema import (
    AllOf,
    AnyOf,
    Comparison,
    EntryDef,
    Not,
    SLTPDef,
    StrategyDef,
)
from app.signals.schema import Signal, TfBreakdown


def evaluate_strategy(
    strat: StrategyDef, ctx: MarketCtx
) -> Signal | None:
    if strat.news_modifier.allow_veto and ctx.blackout:
        return None
    long_hit = strat.entry.long is not None and _eval_node(strat.entry.long, strat.params, ctx)
    short_hit = strat.entry.short is not None and _eval_node(strat.entry.short, strat.params, ctx)
    if long_hit and short_hit:
        # ambiguous; skip
        return None
    if not (long_hit or short_hit):
        return None
    side = "buy" if long_hit else "sell"
    entry = ctx._at(ctx._frame(strat.sl.tf)["close"])
    sl, tp = _compute_sl_tp(side, entry, strat.sl, strat.tp, ctx)

    # Optional news boost
    confidence = 60.0
    news_refs: list[dict] = []
    if strat.news_modifier.allow_boost:
        s = ctx._news_sentiment(30)
        agree = (side == "buy" and s > 0.4) or (side == "sell" and s < -0.4)
        contradict = (side == "buy" and s < -0.6) or (side == "sell" and s > 0.6)
        if contradict and strat.news_modifier.allow_veto:
            return None
        if agree:
            confidence = min(100.0, confidence + 15.0)
            news_refs = [
                {"source": n.get("source"), "headline": n.get("headline"), "url": n.get("url")}
                for n in (ctx.news or [])
                if abs(float(n.get("sentiment", 0.0) or 0.0)) >= 0.4
            ][:5]

    breakdown = _breakdown(strat, ctx)
    return Signal(
        symbol=ctx.symbol,
        side=side,
        confidence=confidence,
        entry=entry,
        sl=round(sl, 4) if sl is not None else None,
        tp=round(tp, 4) if tp is not None else None,
        breakdown=breakdown,
        news_refs=news_refs,
        created_at=ctx.now,
    )


def _eval_node(node: Any, params: dict[str, Any], ctx: MarketCtx) -> bool:
    if isinstance(node, AllOf):
        return all(_eval_node(c, params, ctx) for c in node.all_of)
    if isinstance(node, AnyOf):
        return any(_eval_node(c, params, ctx) for c in node.any_of)
    if isinstance(node, Not):
        return not _eval_node(node.not_, params, ctx)
    if isinstance(node, Comparison):
        if node.op in ("crosses_above", "crosses_below"):
            return _eval_cross(node, params, ctx)
        lhs = ctx.resolve(node.lhs, params)
        rhs = ctx.resolve(node.rhs, params)
        return _cmp(lhs, node.op, rhs)
    raise ValueError(f"unknown node: {node!r}")


def _eval_cross(node: Comparison, params: dict[str, Any], ctx: MarketCtx) -> bool:
    now_l = ctx.resolve(node.lhs, params, offset=0)
    now_r = ctx.resolve(node.rhs, params, offset=0)
    prev_l = ctx.resolve(node.lhs, params, offset=-1)
    prev_r = ctx.resolve(node.rhs, params, offset=-1)
    if any(_is_nan(x) for x in (now_l, now_r, prev_l, prev_r)):
        return False
    if node.op == "crosses_above":
        return prev_l <= prev_r and now_l > now_r
    if node.op == "crosses_below":
        return prev_l >= prev_r and now_l < now_r
    return False


def _is_nan(x: Any) -> bool:
    try:
        return x != x  # NaN != NaN
    except Exception:
        return False


def _cmp(lhs: Any, op: str, rhs: Any) -> bool:
    if _is_nan(lhs) or _is_nan(rhs):
        return False
    if op == "<":
        return lhs < rhs
    if op == ">":
        return lhs > rhs
    if op == "<=":
        return lhs <= rhs
    if op == ">=":
        return lhs >= rhs
    if op == "==":
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    raise ValueError(f"unknown op {op!r}")


def _compute_sl_tp(
    side: str, entry: float, sl_def: SLTPDef, tp_def: SLTPDef, ctx: MarketCtx
) -> tuple[float | None, float | None]:
    sl = _sl_tp_value(side, entry, sl_def, ctx, is_sl=True)
    tp = _sl_tp_value(side, entry, tp_def, ctx, is_sl=False)
    return sl, tp


def _sl_tp_value(side: str, entry: float, d: SLTPDef, ctx: MarketCtx, *, is_sl: bool) -> float | None:
    if d.atr_mult is not None:
        a = ctx._at(ctx.atr(d.tf, d.atr_length))
        if _is_nan(a):
            return None
        delta = d.atr_mult * a
    else:
        delta = (d.pct or 0.0) * entry
    # SL is opposite to side; TP is with side.
    if is_sl:
        return entry - delta if side == "buy" else entry + delta
    return entry + delta if side == "buy" else entry - delta


def _breakdown(strat: StrategyDef, ctx: MarketCtx) -> list[TfBreakdown]:
    """Cheap diagnostic: per-tf RSI/MACD/EMA readouts. Best-effort."""
    out: list[TfBreakdown] = []
    for tf in strat.timeframes or ["15m"]:
        try:
            r = ctx._at(ctx.rsi(tf, 14))
            h = ctx._at(ctx.macd(tf).hist)
            e20 = ctx._at(ctx.ema(tf, 20))
            e50 = ctx._at(ctx.ema(tf, 50))
            out.append(TfBreakdown(
                tf=tf,
                rsi=None if _is_nan(r) else r,
                macd_hist=None if _is_nan(h) else h,
                ema20=None if _is_nan(e20) else e20,
                ema50=None if _is_nan(e50) else e50,
                vote=0,
            ))
        except Exception:
            continue
    return out
