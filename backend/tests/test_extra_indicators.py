import numpy as np
import pandas as pd

from app.indicators.extra import bollinger, donchian, heikin_ashi, sma, supertrend, vwap


def _df(closes):
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "open": np.r_[closes[0], closes[:-1]],
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": 1.0,
        }
    )


def test_bollinger_basis_is_sma_and_widths_are_symmetric():
    closes = np.linspace(100, 200, 60)
    bb = bollinger(pd.Series(closes), length=20, std=2.0)
    assert bb.basis.iloc[-1] == pd.Series(closes).rolling(20, min_periods=20).mean().iloc[-1]
    width_up = bb.upper.iloc[-1] - bb.basis.iloc[-1]
    width_down = bb.basis.iloc[-1] - bb.lower.iloc[-1]
    assert abs(width_up - width_down) < 1e-9


def test_donchian_tracks_rolling_high_low():
    closes = np.r_[np.linspace(100, 110, 30), np.linspace(110, 90, 30)]
    df = _df(closes)
    dc = donchian(df, length=20)
    assert dc.upper.iloc[-1] >= df["high"].iloc[-20:].max() - 1e-9
    assert dc.lower.iloc[-1] <= df["low"].iloc[-20:].min() + 1e-9


def test_vwap_constant_price_equals_price():
    df = _df(np.full(50, 100.0))
    v = vwap(df)
    assert abs(v.iloc[-1] - 100.0) < 1e-9


def test_supertrend_uptrend_returns_plus_one():
    closes = np.linspace(100, 200, 80)
    df = _df(closes)
    s = supertrend(df, length=10, mult=3.0)
    assert s.iloc[-1] == 1


def test_supertrend_downtrend_returns_minus_one():
    closes = np.linspace(200, 100, 80)
    df = _df(closes)
    s = supertrend(df, length=10, mult=3.0)
    assert s.iloc[-1] == -1


def test_heikin_ashi_close_equals_ohlc4():
    closes = np.linspace(100, 110, 10)
    df = _df(closes)
    ha = heikin_ashi(df)
    expected = (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0
    pd.testing.assert_series_equal(ha.close, expected, check_names=False)


def test_sma_simple():
    s = pd.Series(np.arange(20, dtype=float))
    out = sma(s, 5)
    assert out.iloc[-1] == (15 + 16 + 17 + 18 + 19) / 5
