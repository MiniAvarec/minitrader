"""Backtest tests use the runner's internals directly with offline kline data.

We don't hit Binance in unit tests; we patch _fetch_klines to return synthetic
OHLCV for a deterministic outcome.
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app import backtest
from app.backtest import runner as bt
from app.signals.dsl.loader import load_yaml_text


def _ramp_klines(n: int, step: float = 1.0, start: float = 100.0, tf_seconds: int = 900) -> list[dict]:
    base_ms = 1_700_000_000_000
    rows = []
    for i in range(n):
        c = start + i * step
        rows.append(
            {
                "open_time": base_ms + i * tf_seconds * 1000,
                "open": c - step / 2,
                "high": c + 1.0,
                "low": c - 1.0,
                "close": c,
                "volume": 1.0,
                "close_time": base_ms + (i + 1) * tf_seconds * 1000 - 1,
            }
        )
    return rows


@pytest.mark.asyncio
async def test_donchian_breakout_produces_some_trades(monkeypatch):
    yaml_text = """
    name: "Test Donchian"
    description: "test"
    timeframes: ["15m"]
    cooldown_min: 0
    params: {}
    entry:
      long: { lhs: { close: ["15m"] }, op: ">", rhs: { donchian_high: ["15m", 10] } }
      short: { lhs: { close: ["15m"] }, op: "<", rhs: { donchian_low: ["15m", 10] } }
    sl: { atr_mult: 1.0, tf: "15m" }
    tp: { atr_mult: 2.0, tf: "15m" }
    news_modifier: { allow_veto: false, allow_boost: false }
    """
    strat = load_yaml_text(yaml_text)
    # 50 bars flat at 100, then 50 bars rising linearly — should fire long breakouts.
    flat = _ramp_klines(50, step=0.0, start=100.0, tf_seconds=900)
    rise = _ramp_klines(50, step=1.0, start=100.0, tf_seconds=900)
    # adjust open_time of rise so they continue from flat
    base_ms = flat[-1]["close_time"] + 1
    for i, r in enumerate(rise):
        r["open_time"] = base_ms + i * 900_000
        r["close_time"] = r["open_time"] + 900_000 - 1
    klines = flat + rise

    async def fake_fetch(symbol, tf, hours):
        return klines

    monkeypatch.setattr(bt, "_fetch_klines", fake_fetch)
    result = await bt.run(strat, "BTCUSDT", hours=24, notional_usdt=100.0)
    assert len(result.equity_curve) >= 1
    # We expect at least a few trades on a clean uptrend after flat.
    assert len(result.trades) >= 1
    # On a monotonic uptrend, longs should mostly be winners.
    wins = sum(1 for t in result.trades if t.pnl_usdt > 0)
    assert wins >= len(result.trades) // 2


@pytest.mark.asyncio
async def test_runner_handles_no_trades(monkeypatch):
    yaml_text = """
    name: "Never fires"
    timeframes: ["15m"]
    params: {}
    entry:
      long: { lhs: 0, op: ">", rhs: 1 }
      short: { lhs: 0, op: ">", rhs: 1 }
    sl: { atr_mult: 1.0, tf: "15m" }
    tp: { atr_mult: 2.0, tf: "15m" }
    """
    strat = load_yaml_text(yaml_text)
    klines = _ramp_klines(80, step=1.0, start=100.0)

    async def fake_fetch(symbol, tf, hours):
        return klines

    monkeypatch.setattr(bt, "_fetch_klines", fake_fetch)
    result = await bt.run(strat, "BTCUSDT", hours=24, notional_usdt=100.0)
    assert result.trades == []
    assert result.win_rate == 0.0
    assert result.total_pnl_usdt == 0.0
