import numpy as np
import pandas as pd

from app.indicators.ta import atr, ema, evaluate_tf, macd, rsi


def _ramp(n=120, step=1.0, start=100.0):
    return pd.Series(np.arange(n, dtype=float) * step + start)


def test_ema_matches_known_values():
    s = _ramp(50)
    e = ema(s, 10)
    # EMA of a strict ramp converges to last value minus ~length/2 within tolerance
    assert e.iloc[-1] < s.iloc[-1]
    assert abs(e.iloc[-1] - (s.iloc[-1] - 4.5)) < 0.5


def test_rsi_strong_uptrend_above_70():
    s = _ramp(60)
    r = rsi(s, 14)
    assert r.iloc[-1] > 90.0  # monotonic up -> RSI saturates high


def test_rsi_strong_downtrend_below_30():
    s = _ramp(60, step=-1.0)
    r = rsi(s, 14)
    assert r.iloc[-1] < 10.0


def test_macd_bullish_hist_on_uptrend():
    s = _ramp(80)
    m = macd(s)
    assert m.hist.iloc[-1] > 0  # MACD > signal in steady uptrend


def test_atr_positive_and_bounded():
    rng = np.random.default_rng(0)
    closes = pd.Series(np.cumsum(rng.normal(0, 1, 100)) + 100)
    df = pd.DataFrame(
        {
            "open": closes.shift(1).fillna(closes.iloc[0]),
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": 1.0,
        }
    )
    a = atr(df, 14)
    assert a.iloc[-1] > 0
    assert a.iloc[-1] < 10.0


def test_evaluate_tf_returns_zero_for_short_input():
    df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
    out = evaluate_tf(df)
    assert out.bullish == 0
    assert out.rsi is None


def test_evaluate_tf_uptrend_votes_bullish():
    closes = _ramp(80)
    df = pd.DataFrame(
        {"open": closes, "high": closes + 0.5, "low": closes - 0.5, "close": closes, "volume": 1.0}
    )
    out = evaluate_tf(df)
    # MACD hist + EMA stack agree; RSI is overbought (>70) which is a bearish vote.
    # Net: should not be -1 (RSI alone), and price > EMA20 > EMA50 dominates -> bullish.
    assert out.bullish == 1


def test_evaluate_tf_downtrend_votes_bearish():
    closes = _ramp(80, step=-1.0, start=200.0)
    df = pd.DataFrame(
        {"open": closes, "high": closes + 0.5, "low": closes - 0.5, "close": closes, "volume": 1.0}
    )
    out = evaluate_tf(df)
    assert out.bullish == -1
