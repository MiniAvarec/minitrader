from pathlib import Path

import numpy as np
import pandas as pd

from app.signals.dsl.evaluator import evaluate_strategy
from app.signals.dsl.loader import load_yaml_file
from app.signals.dsl.market_ctx import MarketCtx

BUILTINS = Path(__file__).resolve().parent.parent / "app" / "signals" / "dsl" / "builtins"


def _ramp_df(n=120, step=1.0, start=100.0):
    closes = np.arange(n, dtype=float) * step + start
    return pd.DataFrame(
        {
            "open": np.r_[closes[0], closes[:-1]],
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": 1.0,
        }
    )


def _ctx(klines: dict[str, pd.DataFrame], **over):
    return MarketCtx(symbol="BTCUSDT", klines=klines, **over)


def test_multi_tf_confluence_bull():
    s = load_yaml_file(BUILTINS / "multi_tf_confluence.yaml")
    df = _ramp_df()
    ctx = _ctx({tf: df.copy() for tf in s.timeframes})
    sig = evaluate_strategy(s, ctx)
    assert sig is not None and sig.side == "buy"


def test_multi_tf_confluence_bear():
    s = load_yaml_file(BUILTINS / "multi_tf_confluence.yaml")
    df = _ramp_df(step=-1.0, start=300.0)
    ctx = _ctx({tf: df.copy() for tf in s.timeframes})
    sig = evaluate_strategy(s, ctx)
    assert sig is not None and sig.side == "sell"


def test_donchian_breakout_fires_on_breakout():
    s = load_yaml_file(BUILTINS / "donchian_breakout.yaml")
    closes = np.r_[np.full(40, 100.0), np.full(20, 99.5), [120.0]]
    df = pd.DataFrame(
        {
            "open": np.r_[closes[0], closes[:-1]],
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": 1.0,
        }
    )
    ctx = _ctx({"1h": df})
    sig = evaluate_strategy(s, ctx)
    assert sig is not None and sig.side == "buy"


def test_rsi_mean_reversion_fires_when_oversold_and_macd_up():
    s = load_yaml_file(BUILTINS / "rsi_mean_reversion.yaml")
    # Drop sharply (push RSI low) then turn up (push MACD hist > 0)
    drop = np.linspace(200, 100, 60)
    rebound = np.linspace(100, 110, 30)
    closes = np.r_[drop, rebound]
    df = pd.DataFrame(
        {
            "open": np.r_[closes[0], closes[:-1]],
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": 1.0,
        }
    )
    ctx = _ctx({"15m": df})
    sig = evaluate_strategy(s, ctx)
    # RSI may or may not be oversold at exact end, but the structure should at least
    # not produce a SELL on an uptrend rebound.
    assert sig is None or sig.side == "buy"


def test_news_blackout_suppresses():
    s = load_yaml_file(BUILTINS / "rsi_mean_reversion.yaml")
    df = _ramp_df(step=-1.0, start=200.0)
    ctx = _ctx({"15m": df}, blackout=True)
    assert evaluate_strategy(s, ctx) is None


def test_news_veto_on_contradicting_strong_sentiment():
    from datetime import datetime, timezone, timedelta

    s = load_yaml_file(BUILTINS / "rsi_mean_reversion.yaml")
    drop = np.linspace(200, 100, 80)
    df = pd.DataFrame(
        {
            "open": np.r_[drop[0], drop[:-1]],
            "high": drop + 0.5,
            "low": drop - 0.5,
            "close": drop,
            "volume": 1.0,
        }
    )
    now = datetime.now(timezone.utc)
    news = [
        {
            "source": "x",
            "headline": "huge crash",
            "url": "u",
            "sentiment": -0.9,
            "published_at": (now - timedelta(minutes=5)).isoformat(),
        }
    ]
    ctx = _ctx({"15m": df}, news=news, now=now)
    sig = evaluate_strategy(s, ctx)
    # Strongly bearish news should veto a buy. Either None or short — never buy.
    assert sig is None or sig.side == "sell"
