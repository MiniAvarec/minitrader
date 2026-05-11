"""Build the full evaluation context for one Order.

The LLMs receive deal facts + strategy + multi-timeframe candles around entry
and exit (or "now" for open deals) + derived indicators + user risk config.
Everything is plain dicts so prompts.py can serialize into structured markdown.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import to_ccxt_symbol
from app.brokers.factory import get_broker_for_user
from app.db.models import Order, RiskConfig, Signal, Strategy, User


# ---------- pure indicator helpers (no new deps) ----------


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(candles: list[dict], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def _excursion(
    candles: list[dict], entry_price: float, side: str
) -> dict[str, float | None]:
    """Max favorable / adverse excursion (in % of entry) since entry."""
    if not candles or not entry_price:
        return {"max_favorable_pct": None, "max_adverse_pct": None}
    is_long = side == "buy"
    best = -1e18
    worst = 1e18
    for c in candles:
        best = max(best, c["high"] if is_long else -c["low"])
        worst = min(worst, c["low"] if is_long else -c["high"])
    best_price = best if is_long else -best
    worst_price = worst if is_long else -worst
    mfe = (best_price - entry_price) / entry_price * 100.0 * (1 if is_long else -1)
    mae = (worst_price - entry_price) / entry_price * 100.0 * (1 if is_long else -1)
    return {"max_favorable_pct": round(mfe, 3), "max_adverse_pct": round(mae, 3)}


def _trim_candle(c: dict) -> dict:
    """Compact candle for prompt — drop volume noise scale, fixed decimals."""
    return {
        "t": c["open_time"],
        "o": c["open"],
        "h": c["high"],
        "l": c["low"],
        "c": c["close"],
        "v": round(c.get("volume", 0.0), 4),
    }


# ---------- main entry point ----------


async def build_eval_context(
    db: AsyncSession,
    user: User,
    order: Order,
) -> dict[str, Any]:
    """Assemble everything the LLM should know about this single deal."""
    is_open = order.status != "closed"
    duration_s: int | None = None
    if order.closed_at and order.created_at:
        duration_s = max(0, int((order.closed_at - order.created_at).total_seconds()))
    roi_pct: float | None = None
    if order.notional_usdt:
        roi_pct = float(order.realized_pnl_usdt) / float(order.notional_usdt) * 100.0
    r_multiple: float | None = None
    if order.sl and order.qty and order.entry_price:
        risk_per_unit = abs(order.entry_price - order.sl)
        risk_usdt = risk_per_unit * order.qty
        if risk_usdt > 0:
            r_multiple = float(order.realized_pnl_usdt) / risk_usdt

    # ---- strategy info ----
    strategy_name: str | None = None
    strategy_yaml: str | None = None
    if order.signal_id is not None:
        srow = (
            await db.execute(
                select(Strategy.name, Strategy.code)
                .join(Signal, Signal.strategy_id == Strategy.id)
                .where(Signal.id == order.signal_id)
            )
        ).first()
        if srow is not None:
            strategy_name, strategy_yaml = srow

    # ---- risk config ----
    rc = (
        await db.execute(select(RiskConfig).where(RiskConfig.user_id == user.id))
    ).scalar_one_or_none()
    risk_block = (
        {
            "max_notional_usdt": rc.max_notional_usdt,
            "daily_loss_limit_usdt": rc.daily_loss_limit_usdt,
            "max_concurrent_positions": rc.max_concurrent_positions,
            "require_sl_tp": rc.require_sl_tp,
        }
        if rc
        else None
    )

    # ---- market candles around entry/exit ----
    candles_4h: list[dict] = []
    candles_1h_pre: list[dict] = []
    candles_1h_post: list[dict] = []
    candles_5m: list[dict] = []
    atr_at_entry: float | None = None
    rsi_at_entry: float | None = None
    volume_ratio_at_entry: float | None = None
    excursion: dict[str, float | None] = {
        "max_favorable_pct": None,
        "max_adverse_pct": None,
    }
    current_price: float | None = None
    fetch_error: str | None = None

    broker = await get_broker_for_user(db, user.id, order.exchange)
    if broker is None:
        fetch_error = f"No API key on file for {order.exchange} — market context skipped."
    else:
        try:
            ccxt_sym = to_ccxt_symbol(order.exchange, order.symbol)
            entry_ms = int(order.created_at.timestamp() * 1000)
            end_anchor_ms = (
                int(order.closed_at.timestamp() * 1000)
                if order.closed_at
                else None
            )

            # Pre-entry context: 50 1h candles ending at entry; 30 4h for higher-tf;
            # 24 5m candles ending at entry for fine-grain.
            candles_1h_pre = await broker.fetch_klines(
                ccxt_sym, "1h", end_ms=entry_ms, limit=50
            )
            candles_4h = await broker.fetch_klines(
                ccxt_sym, "4h", end_ms=entry_ms, limit=30
            )
            candles_5m = await broker.fetch_klines(
                ccxt_sym, "5m", end_ms=entry_ms, limit=24
            )
            # Post-entry context: 1h candles up to close (closed) or "now" (open).
            candles_1h_post = await broker.fetch_klines(
                ccxt_sym, "1h", end_ms=end_anchor_ms, limit=50
            )

            # Derived indicators at-entry.
            if candles_1h_pre:
                closes = [c["close"] for c in candles_1h_pre]
                vols = [c.get("volume", 0.0) for c in candles_1h_pre]
                rsi_at_entry = _rsi(closes, 14)
                atr_at_entry = _atr(candles_1h_pre, 14)
                sma_vol = _sma(vols[:-1], 20) if len(vols) > 1 else None
                if sma_vol and sma_vol > 0:
                    volume_ratio_at_entry = round(vols[-1] / sma_vol, 3)

            excursion = _excursion(
                candles_1h_post, order.entry_price, order.side.value
            )

            if is_open:
                try:
                    current_price = await broker.mark_price(order.symbol)
                except Exception:
                    current_price = None
        except Exception as e:
            fetch_error = f"{type(e).__name__}: {e}"
        finally:
            try:
                await broker.close()
            except Exception:
                pass

    # ATR-distance from entry to SL.
    sl_distance_atr: float | None = None
    if atr_at_entry and order.sl:
        sl_distance_atr = abs(order.entry_price - order.sl) / atr_at_entry

    # Unrealized PnL for open deals (rough — uses current_price if available).
    unrealized_pnl_usdt: float | None = None
    if is_open and current_price is not None and order.qty:
        sign = 1.0 if order.side.value == "buy" else -1.0
        unrealized_pnl_usdt = (current_price - order.entry_price) * order.qty * sign

    # ---- strategy params (parse YAML to a small dict) ----
    strategy_params: dict | None = None
    if strategy_yaml:
        try:
            parsed = yaml.safe_load(strategy_yaml) or {}
            if isinstance(parsed, dict):
                # Keep only header-ish keys to bound prompt size.
                strategy_params = {
                    k: parsed.get(k)
                    for k in ("name", "description", "timeframes", "entry", "exit", "risk")
                    if k in parsed
                }
        except Exception:
            strategy_params = None

    return {
        "is_open": is_open,
        "now_iso": datetime.now(timezone.utc).isoformat(),
        "deal": {
            "id": order.id,
            "exchange": order.exchange,
            "symbol": order.symbol,
            "side": order.side.value,
            "status": order.status,
            "qty": order.qty,
            "notional_usdt": order.notional_usdt,
            "entry_price": order.entry_price,
            "exit_price": order.exit_price,
            "sl": order.sl,
            "tp": order.tp,
            "fee_usdt": order.fee_usdt or 0.0,
            "realized_pnl_usdt": order.realized_pnl_usdt,
            "unrealized_pnl_usdt": unrealized_pnl_usdt,
            "current_price": current_price,
            "roi_pct": roi_pct,
            "r_multiple": r_multiple,
            "duration_s": duration_s,
            "created_at": order.created_at.isoformat(),
            "closed_at": order.closed_at.isoformat() if order.closed_at else None,
            "notes": order.notes,
            "tags": list(order.tags or []),
        },
        "strategy": {
            "name": strategy_name,
            "params": strategy_params,
        },
        "risk_limits": risk_block,
        "derived": {
            "rsi_14_at_entry": (round(rsi_at_entry, 2) if rsi_at_entry is not None else None),
            "atr_14_at_entry": (round(atr_at_entry, 6) if atr_at_entry is not None else None),
            "sl_distance_atr": (round(sl_distance_atr, 3) if sl_distance_atr is not None else None),
            "volume_ratio_at_entry": volume_ratio_at_entry,
            **excursion,
        },
        "candles": {
            "tf_4h_pre_entry": [_trim_candle(c) for c in candles_4h],
            "tf_1h_pre_entry": [_trim_candle(c) for c in candles_1h_pre],
            "tf_5m_pre_entry": [_trim_candle(c) for c in candles_5m],
            "tf_1h_post_entry": [_trim_candle(c) for c in candles_1h_post],
        },
        "market_data_error": fetch_error,
    }
