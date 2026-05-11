"""MarketCtx — the runtime view a strategy sees.

Holds per-tf kline DataFrames and lazily computes indicators on demand,
caching them so multiple references in one rule tree share work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from app.indicators import extra as extra_ta
from app.indicators import ta


@dataclass
class MarketCtx:
    symbol: str
    klines: dict[str, pd.DataFrame]  # tf -> OHLCV frame
    news: list[dict] = field(default_factory=list)
    blackout: bool = False
    fear_greed: float | None = None      # latest Crypto F&G value 0..100
    reddit_hype: float | None = None     # ctx.symbol's hype score 0..1
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # if set, all *_value() reads use this index instead of the last bar.
    # Used by the backtester to walk forward.
    index: int = -1

    _cache: dict[tuple, Any] = field(default_factory=dict, init=False, repr=False)

    # ---------- frame helpers ----------

    def _frame(self, tf: str) -> pd.DataFrame:
        df = self.klines.get(tf)
        if df is None:
            raise KeyError(f"no klines for tf {tf!r}")
        return df

    def _at(self, series: pd.Series) -> float:
        if len(series) == 0:
            return float("nan")
        idx = self.index if self.index < 0 else min(self.index, len(series) - 1)
        return float(series.iloc[idx])

    def _at_offset(self, series: pd.Series, offset: int) -> float:
        """offset of -1 means 'one bar before current', etc."""
        if len(series) == 0:
            return float("nan")
        if self.index < 0:
            target = self.index + offset
        else:
            target = self.index + offset
        if abs(target) > len(series):
            return float("nan")
        return float(series.iloc[target])

    # ---------- indicator getters (cached series) ----------

    def _series(self, key: tuple, fn) -> pd.Series:
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def rsi(self, tf: str, length: int) -> pd.Series:
        return self._series(("rsi", tf, length), lambda: ta.rsi(self._frame(tf)["close"], length))

    def macd(self, tf: str):
        return self._series(("macd", tf), lambda: ta.macd(self._frame(tf)["close"]))

    def ema(self, tf: str, length: int) -> pd.Series:
        return self._series(("ema", tf, length), lambda: ta.ema(self._frame(tf)["close"], length))

    def sma(self, tf: str, length: int) -> pd.Series:
        return self._series(("sma", tf, length), lambda: extra_ta.sma(self._frame(tf)["close"], length))

    def atr(self, tf: str, length: int = 14) -> pd.Series:
        return self._series(("atr", tf, length), lambda: ta.atr(self._frame(tf), length))

    def bollinger(self, tf: str, length: int, std: float):
        return self._series(
            ("bollinger", tf, length, std),
            lambda: extra_ta.bollinger(self._frame(tf)["close"], length, std),
        )

    def donchian(self, tf: str, length: int):
        return self._series(("donchian", tf, length), lambda: extra_ta.donchian(self._frame(tf), length))

    def vwap(self, tf: str) -> pd.Series:
        return self._series(("vwap", tf), lambda: extra_ta.vwap(self._frame(tf)))

    def supertrend(self, tf: str, length: int, mult: float) -> pd.Series:
        return self._series(("supertrend", tf, length, mult), lambda: extra_ta.supertrend(self._frame(tf), length, mult))

    def heikin_ashi(self, tf: str):
        return self._series(("ha", tf), lambda: extra_ta.heikin_ashi(self._frame(tf)))

    def stochrsi(
        self,
        tf: str,
        rsi_len: int,
        stoch_len: int,
        k_smooth: int,
        d_smooth: int,
    ):
        return self._series(
            ("stochrsi", tf, rsi_len, stoch_len, k_smooth, d_smooth),
            lambda: extra_ta.stochrsi(
                self._frame(tf)["close"], rsi_len, stoch_len, k_smooth, d_smooth
            ),
        )

    # ---------- ValueRef resolution (used by evaluator) ----------

    def resolve(self, ref: Any, params: dict[str, Any], *, offset: int = 0) -> float | bool:
        """Return the scalar value of a ValueRef at (current_index + offset)."""
        if isinstance(ref, (int, float, bool)):
            return ref
        if isinstance(ref, str):
            return ref  # string literal — only useful as RHS of ==/!=
        if not isinstance(ref, dict) or len(ref) != 1:
            raise ValueError(f"bad value ref: {ref!r}")
        [(name, args)] = ref.items()
        if args is None:
            args = []
        if not isinstance(args, list):
            args = [args]

        # convenience getter that pulls the last (or offset) value of a series
        def last(s: pd.Series) -> float:
            return self._at_offset(s, offset)

        if name == "param":
            return params.get(args[0])
        if name == "rsi":
            return last(self.rsi(args[0], int(args[1])))
        if name == "macd_line":
            return last(self.macd(args[0]).macd)
        if name == "macd_signal":
            return last(self.macd(args[0]).signal)
        if name == "macd_hist":
            return last(self.macd(args[0]).hist)
        if name == "ema":
            return last(self.ema(args[0], int(args[1])))
        if name == "sma":
            return last(self.sma(args[0], int(args[1])))
        if name == "atr":
            return last(self.atr(args[0], int(args[1])))
        if name in ("close", "open", "high", "low", "volume"):
            return last(self._frame(args[0])[name])
        if name in ("bb_upper", "bb_basis", "bb_lower"):
            bb = self.bollinger(args[0], int(args[1]), float(args[2]))
            attr = {"bb_upper": "upper", "bb_basis": "basis", "bb_lower": "lower"}[name]
            return last(getattr(bb, attr))
        if name == "donchian_high":
            return last(self.donchian(args[0], int(args[1])).upper)
        if name == "donchian_low":
            return last(self.donchian(args[0], int(args[1])).lower)
        if name == "vwap":
            return last(self.vwap(args[0]))
        if name == "supertrend":
            return last(self.supertrend(args[0], int(args[1]), float(args[2])))
        if name in ("ha_open", "ha_close", "ha_high", "ha_low"):
            ha = self.heikin_ashi(args[0])
            attr = {"ha_open": "open", "ha_close": "close", "ha_high": "high", "ha_low": "low"}[name]
            return last(getattr(ha, attr))
        if name in ("stochrsi_k", "stochrsi_d"):
            sr = self.stochrsi(
                args[0],
                int(args[1]),
                int(args[2]),
                int(args[3]),
                int(args[4]),
            )
            return last(sr.k if name == "stochrsi_k" else sr.d)
        if name == "news_sentiment":
            minutes = int(args[0])
            return self._news_sentiment(minutes)
        if name == "news_blackout":
            return bool(self.blackout)
        if name == "fear_greed":
            # Neutral default (50) keeps comparisons sensible when the index
            # isn't available yet, instead of forcing strategies to handle NaN.
            return float(self.fear_greed) if self.fear_greed is not None else 50.0
        if name == "reddit_hype":
            return float(self.reddit_hype) if self.reddit_hype is not None else 0.0
        if name == "minute_of_hour":
            return self.now.minute
        if name == "hour_of_day_utc":
            return self.now.hour
        raise ValueError(f"unknown indicator {name!r}")

    def _news_sentiment(self, minutes: int) -> float:
        if not self.news:
            return 0.0
        cutoff = self.now - timedelta(minutes=minutes)
        scores: list[float] = []
        for n in self.news:
            published = n.get("published_at")
            if isinstance(published, str):
                try:
                    published = datetime.fromisoformat(published)
                except ValueError:
                    continue
            if not isinstance(published, datetime):
                continue
            if published < cutoff:
                continue
            scores.append(float(n.get("sentiment", 0.0) or 0.0))
        if not scores:
            return 0.0
        return sum(scores) / len(scores)
