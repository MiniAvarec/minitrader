from datetime import datetime, timedelta, timezone

import numpy as np

from app.signals.engine import evaluate


def _ramp_klines(n=120, step=1.0, start=100.0):
    return [
        {
            "open": start + i * step,
            "high": start + i * step + 0.5,
            "low": start + i * step - 0.5,
            "close": start + i * step,
            "volume": 1.0,
        }
        for i in range(n)
    ]


def test_no_signal_with_no_data():
    sig = evaluate("BTCUSDT", {"1m": [], "3m": [], "15m": [], "1h": []})
    assert sig is None


def test_buy_signal_when_all_tfs_bullish():
    klines = _ramp_klines(120, step=1.0)
    tfk = {"1m": klines, "3m": klines, "15m": klines, "1h": klines}
    sig = evaluate("BTCUSDT", tfk, news=[])
    assert sig is not None
    assert sig.side == "buy"
    assert sig.entry > 0
    assert sig.sl is not None and sig.tp is not None
    assert sig.sl < sig.entry < sig.tp


def test_sell_signal_when_all_tfs_bearish():
    klines = _ramp_klines(120, step=-1.0, start=300.0)
    tfk = {"1m": klines, "3m": klines, "15m": klines, "1h": klines}
    sig = evaluate("BTCUSDT", tfk, news=[])
    assert sig is not None
    assert sig.side == "sell"
    assert sig.tp < sig.entry < sig.sl


def test_blackout_suppresses_signal():
    klines = _ramp_klines(120, step=1.0)
    tfk = {"1m": klines, "3m": klines, "15m": klines, "1h": klines}
    sig = evaluate("BTCUSDT", tfk, news=[], blackout=True)
    assert sig is None


def test_news_can_veto_a_signal():
    klines = _ramp_klines(120, step=1.0)
    tfk = {"1m": klines, "3m": klines, "15m": klines, "1h": klines}
    now = datetime.now(timezone.utc)
    news = [{
        "source": "finnhub",
        "headline": "huge crash",
        "url": "u",
        "sentiment": -0.9,  # strongly bearish, contradicts a buy
        "published_at": (now - timedelta(minutes=5)).isoformat(),
    }]
    sig = evaluate("BTCUSDT", tfk, news=news, now=now)
    assert sig is None


def test_news_boost_raises_confidence():
    klines = _ramp_klines(120, step=1.0)
    tfk = {"1m": klines, "3m": klines, "15m": klines, "1h": klines}
    now = datetime.now(timezone.utc)
    base = evaluate("BTCUSDT", tfk, news=[], now=now)
    news = [{
        "source": "cryptopanic",
        "headline": "rally to ATH",
        "url": "u",
        "sentiment": 0.8,
        "published_at": (now - timedelta(minutes=5)).isoformat(),
    }]
    boosted = evaluate("BTCUSDT", tfk, news=news, now=now)
    assert boosted.confidence > base.confidence
    assert len(boosted.news_refs) == 1
