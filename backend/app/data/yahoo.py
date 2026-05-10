"""Yahoo Finance helpers for context (e.g. SPY/DXY for risk-on/off).

We don't use Yahoo for live crypto klines — Binance WS is authoritative.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

log = logging.getLogger("yahoo")


async def fetch_history(symbol: str, period: str = "5d", interval: str = "15m") -> pd.DataFrame:
    """Run yfinance in a thread (it's blocking)."""
    import yfinance as yf

    def _fetch() -> pd.DataFrame:
        try:
            df = yf.download(
                symbol, period=period, interval=interval, progress=False, auto_adjust=False
            )
            return df
        except Exception as e:
            log.warning("yahoo %s failed: %s", symbol, e)
            return pd.DataFrame()

    return await asyncio.to_thread(_fetch)


async def market_regime() -> dict:
    """Cheap risk-on/off gauge: SPY 1h trend + DXY 1h trend."""
    spy, dxy = await asyncio.gather(
        fetch_history("SPY", period="2d", interval="60m"),
        fetch_history("DX-Y.NYB", period="2d", interval="60m"),
    )

    def _trend(df: pd.DataFrame) -> str:
        if df is None or df.empty or "Close" not in df.columns or len(df) < 5:
            return "unknown"
        last = float(df["Close"].iloc[-1])
        first = float(df["Close"].iloc[0])
        if last > first * 1.002:
            return "up"
        if last < first * 0.998:
            return "down"
        return "flat"

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "spy_trend": _trend(spy),
        "dxy_trend": _trend(dxy),
    }
