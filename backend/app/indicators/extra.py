"""Additional indicators used by built-in strategies.

Pure pandas/numpy, same style as ta.py — no pandas-ta dependency.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.indicators.ta import atr as _atr, ema as _ema, rsi as _rsi


@dataclass
class BollingerResult:
    upper: pd.Series
    basis: pd.Series
    lower: pd.Series


def bollinger(close: pd.Series, length: int = 20, std: float = 2.0) -> BollingerResult:
    basis = close.rolling(length, min_periods=length).mean()
    sigma = close.rolling(length, min_periods=length).std(ddof=0)
    return BollingerResult(
        upper=basis + std * sigma,
        basis=basis,
        lower=basis - std * sigma,
    )


@dataclass
class DonchianResult:
    upper: pd.Series  # rolling N-bar high
    lower: pd.Series  # rolling N-bar low
    middle: pd.Series


def donchian(df: pd.DataFrame, length: int = 20) -> DonchianResult:
    upper = df["high"].rolling(length, min_periods=length).max()
    lower = df["low"].rolling(length, min_periods=length).min()
    return DonchianResult(upper=upper, lower=lower, middle=(upper + lower) / 2.0)


def vwap(df: pd.DataFrame) -> pd.Series:
    """Cumulative VWAP from the start of the supplied frame.

    For an intraday VWAP, callers should slice df to the desired session
    window (e.g. UTC-day start to now) before computing.
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]
    return pv.cumsum() / df["volume"].cumsum().replace(0, np.nan)


def supertrend(df: pd.DataFrame, length: int = 10, mult: float = 3.0) -> pd.Series:
    """Returns a Series of +1 (uptrend) / -1 (downtrend).

    Standard SuperTrend: midline = (high+low)/2; bands = midline ± mult*ATR.
    Trend flips when close crosses the active band.
    """
    a = _atr(df, length)
    mid = (df["high"] + df["low"]) / 2.0
    upper = mid + mult * a
    lower = mid - mult * a
    direction = pd.Series(np.nan, index=df.index)
    final_upper = upper.copy()
    final_lower = lower.copy()
    prev_dir = 1
    for i in range(len(df)):
        if i == 0 or pd.isna(a.iloc[i]):
            direction.iloc[i] = prev_dir
            continue
        # roll bands forward (Tradingview-style)
        if upper.iloc[i] < final_upper.iloc[i - 1] or df["close"].iloc[i - 1] > final_upper.iloc[i - 1]:
            pass  # use computed upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]
        if lower.iloc[i] > final_lower.iloc[i - 1] or df["close"].iloc[i - 1] < final_lower.iloc[i - 1]:
            pass
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]
        if df["close"].iloc[i] > final_upper.iloc[i]:
            prev_dir = 1
        elif df["close"].iloc[i] < final_lower.iloc[i]:
            prev_dir = -1
        direction.iloc[i] = prev_dir
    return direction


@dataclass
class HaResult:
    open: pd.Series
    high: pd.Series
    low: pd.Series
    close: pd.Series


def heikin_ashi(df: pd.DataFrame) -> HaResult:
    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0
    ha_open = pd.Series(np.nan, index=df.index)
    if len(df) > 0:
        ha_open.iloc[0] = (df["open"].iloc[0] + df["close"].iloc[0]) / 2.0
        for i in range(1, len(df)):
            ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2.0
    ha_high = pd.concat([df["high"], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df["low"], ha_open, ha_close], axis=1).min(axis=1)
    return HaResult(open=ha_open, high=ha_high, low=ha_low, close=ha_close)


def sma(close: pd.Series, length: int) -> pd.Series:
    return close.rolling(length, min_periods=length).mean()


@dataclass
class StochRsiResult:
    k: pd.Series
    d: pd.Series


def stochrsi(
    close: pd.Series,
    rsi_len: int = 14,
    stoch_len: int = 14,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> StochRsiResult:
    """Stochastic RSI — TradingView convention.

    1. Compute RSI(rsi_len) over close
    2. Take the rolling min/max of RSI over stoch_len bars
    3. Scale into [0..100] => raw K
    4. K = SMA(raw, k_smooth), D = SMA(K, d_smooth)
    """
    r = _rsi(close, rsi_len)
    lowest = r.rolling(stoch_len, min_periods=stoch_len).min()
    highest = r.rolling(stoch_len, min_periods=stoch_len).max()
    raw = 100.0 * (r - lowest) / (highest - lowest).replace(0, np.nan)
    k = raw.rolling(k_smooth, min_periods=k_smooth).mean()
    d = k.rolling(d_smooth, min_periods=d_smooth).mean()
    return StochRsiResult(k=k, d=d)
