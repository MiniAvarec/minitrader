"""Walk-forward backtester for the YAML DSL.

For each closed bar of the dominant timeframe (from sl.tf), build a
MarketCtx truncated to that bar via MarketCtx.index, run the evaluator,
and on a signal open a virtual position. Close on the first subsequent
bar whose high/low touches TP/SL. Compute trade stats + equity curve.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pandas as pd

from app.config import get_settings
from app.signals.dsl.evaluator import evaluate_strategy
from app.signals.dsl.market_ctx import MarketCtx
from app.signals.dsl.schema import StrategyDef


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    side: str
    entry: float
    exit: float
    sl: float | None
    tp: float | None
    pnl_pct: float
    pnl_usdt: float
    outcome: str  # "tp" | "sl" | "timeout"


@dataclass
class BacktestResult:
    symbol: str
    hours: int
    trades: list[Trade]
    win_rate: float
    total_pnl_usdt: float
    total_pnl_pct: float
    max_drawdown_pct: float
    equity_curve: list[dict]


# Map timeframe → seconds + Binance interval label
_TF_SECONDS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}


def _rest_base() -> str:
    return (
        "https://testnet.binancefuture.com"
        if get_settings().BINANCE_USE_TESTNET
        else "https://fapi.binance.com"
    )


async def _fetch_klines(symbol: str, tf: str, hours: int) -> list[dict]:
    bars_needed = max(200, (hours * 3600) // _TF_SECONDS.get(tf, 900) + 50)
    bars_needed = min(bars_needed, 1500)
    base = _rest_base()
    out: list[dict] = []
    end_ms: int | None = None
    async with httpx.AsyncClient(base_url=base, timeout=20.0) as client:
        while bars_needed > 0:
            limit = min(bars_needed, 500)
            params: dict[str, Any] = {"symbol": symbol, "interval": tf, "limit": limit}
            if end_ms is not None:
                params["endTime"] = end_ms
            r = await client.get("/fapi/v1/klines", params=params)
            r.raise_for_status()
            rows = r.json()
            if not rows:
                break
            chunk = [
                {
                    "open_time": int(x[0]),
                    "open": float(x[1]),
                    "high": float(x[2]),
                    "low": float(x[3]),
                    "close": float(x[4]),
                    "volume": float(x[5]),
                    "close_time": int(x[6]),
                }
                for x in rows
            ]
            out = chunk + out
            end_ms = chunk[0]["open_time"] - 1
            bars_needed -= len(chunk)
            if len(chunk) < limit:
                break
    return out


async def run(
    strategy: StrategyDef,
    symbol: str,
    *,
    hours: int = 168,
    notional_usdt: float = 100.0,
) -> BacktestResult:
    tfs = sorted(set(strategy.timeframes) | {strategy.sl.tf, strategy.tp.tf})
    raw = {tf: await _fetch_klines(symbol, tf, hours) for tf in tfs}
    frames = {
        tf: pd.DataFrame(rows)[["open", "high", "low", "close", "volume"]].astype(float)
        if rows
        else pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        for tf, rows in raw.items()
    }
    times: dict[str, list[int]] = {tf: [r["open_time"] for r in raw[tf]] for tf in tfs}

    dom_tf = strategy.sl.tf
    dom_n = len(frames[dom_tf])
    if dom_n < 60:
        return BacktestResult(
            symbol=symbol, hours=hours, trades=[], win_rate=0.0,
            total_pnl_usdt=0.0, total_pnl_pct=0.0, max_drawdown_pct=0.0,
            equity_curve=[{"t": int(datetime.now(timezone.utc).timestamp() * 1000), "equity": 0.0}],
        )

    trades: list[Trade] = []
    equity = 0.0
    peak = 0.0
    max_dd_pct = 0.0
    equity_curve: list[dict] = []
    open_pos: dict | None = None

    for i in range(50, dom_n):
        # Truncate frames to bars up-to-and-including i (in dominant TF time).
        cutoff_ms = times[dom_tf][i]
        truncated = {}
        for tf in tfs:
            ts = times[tf]
            # rfind first index whose open_time > cutoff
            cut = len(ts)
            for j in range(len(ts) - 1, -1, -1):
                if ts[j] <= cutoff_ms:
                    cut = j + 1
                    break
            truncated[tf] = frames[tf].iloc[:cut]

        # If a position is open, check whether the current bar (i) hits SL/TP.
        if open_pos:
            bar = frames[dom_tf].iloc[i]
            hit = _check_fill(open_pos, float(bar["high"]), float(bar["low"]))
            if hit is not None:
                exit_price, outcome = hit
                pnl_pct = (
                    (exit_price - open_pos["entry"]) / open_pos["entry"]
                    if open_pos["side"] == "buy"
                    else (open_pos["entry"] - exit_price) / open_pos["entry"]
                )
                pnl_usdt = pnl_pct * notional_usdt
                trades.append(
                    Trade(
                        entry_time=_iso(open_pos["entry_ms"]),
                        exit_time=_iso(times[dom_tf][i]),
                        side=open_pos["side"],
                        entry=open_pos["entry"],
                        exit=exit_price,
                        sl=open_pos["sl"],
                        tp=open_pos["tp"],
                        pnl_pct=pnl_pct,
                        pnl_usdt=pnl_usdt,
                        outcome=outcome,
                    )
                )
                equity += pnl_usdt
                peak = max(peak, equity)
                if peak > 0:
                    max_dd_pct = max(max_dd_pct, (peak - equity) / peak)
                equity_curve.append({"t": times[dom_tf][i], "equity": equity})
                open_pos = None

        if open_pos:
            continue  # don't open a second position while one is live

        ctx = MarketCtx(
            symbol=symbol,
            klines=truncated,
            news=[],
            blackout=False,
            now=datetime.fromtimestamp(times[dom_tf][i] / 1000, tz=timezone.utc),
        )
        sig = evaluate_strategy(strategy, ctx)
        if sig is None:
            continue
        open_pos = {
            "side": sig.side,
            "entry": sig.entry,
            "sl": sig.sl,
            "tp": sig.tp,
            "entry_ms": times[dom_tf][i],
        }

    total_pct = equity / notional_usdt if notional_usdt > 0 else 0.0
    win_rate = (
        sum(1 for t in trades if t.pnl_usdt > 0) / len(trades) if trades else 0.0
    )
    if not equity_curve:
        equity_curve = [{"t": int(datetime.now(timezone.utc).timestamp() * 1000), "equity": 0.0}]
    return BacktestResult(
        symbol=symbol,
        hours=hours,
        trades=trades,
        win_rate=win_rate,
        total_pnl_usdt=equity,
        total_pnl_pct=total_pct,
        max_drawdown_pct=max_dd_pct,
        equity_curve=equity_curve,
    )


def _check_fill(pos: dict, bar_high: float, bar_low: float) -> tuple[float, str] | None:
    sl, tp, side = pos["sl"], pos["tp"], pos["side"]
    if side == "buy":
        if sl is not None and bar_low <= sl:
            return sl, "sl"
        if tp is not None and bar_high >= tp:
            return tp, "tp"
    else:
        if sl is not None and bar_high >= sl:
            return sl, "sl"
        if tp is not None and bar_low <= tp:
            return tp, "tp"
    return None


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
