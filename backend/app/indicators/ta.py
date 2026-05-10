"""Pure indicator functions. Take DataFrame[open,high,low,close,volume], return scalars/series.

Implementations are vectorized numpy/pandas (no pandas-ta dependency at the test path
so unit tests don't need the lib's binary deps). Results match the standard formulas:

- RSI: Wilder's smoothing, period 14
- MACD: EMA(12) - EMA(26), signal EMA(9), histogram = macd - signal
- EMA: standard adj=False ewm
- ATR: Wilder's smoothing of true range, period 14
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out


@dataclass
class MacdResult:
    macd: pd.Series
    signal: pd.Series
    hist: pd.Series


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> MacdResult:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return MacdResult(macd=macd_line, signal=signal_line, hist=hist)


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


@dataclass
class TfReadout:
    rsi: float | None
    macd_hist: float | None
    ema20: float | None
    ema50: float | None
    close: float | None
    bullish: int  # +1 / 0 / -1 vote contribution from this TF


def evaluate_tf(df: pd.DataFrame) -> TfReadout:
    """Score one timeframe to a vote. df has at least ~60 rows of klines."""
    if df is None or df.empty or len(df) < 60:
        return TfReadout(None, None, None, None, None, 0)
    close = df["close"]
    r = float(rsi(close, 14).iloc[-1])
    m = macd(close)
    h = float(m.hist.iloc[-1])
    e20 = float(ema(close, 20).iloc[-1])
    e50 = float(ema(close, 50).iloc[-1])
    c = float(close.iloc[-1])

    score = 0
    # RSI: oversold = bullish, overbought = bearish
    if r < 30:
        score += 1
    elif r > 70:
        score -= 1
    # MACD histogram sign
    if h > 0:
        score += 1
    elif h < 0:
        score -= 1
    # Price vs EMA20 / EMA50 stack
    if c > e20 > e50:
        score += 1
    elif c < e20 < e50:
        score -= 1

    # Collapse to single vote
    vote = 1 if score >= 2 else (-1 if score <= -2 else 0)
    return TfReadout(rsi=r, macd_hist=h, ema20=e20, ema50=e50, close=c, bullish=vote)
