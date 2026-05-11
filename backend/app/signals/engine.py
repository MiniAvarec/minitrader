"""Strategy dispatcher.

The hardcoded multi-TF agreement that lived here in v1 is now the
`multi_tf_confluence` built-in YAML strategy. This module just orchestrates:

    klines (per tf)  +  news  +  blackout
            └────► MarketCtx
                       └────► evaluate_strategy(strat, ctx) → Signal | None
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.signals.dsl.evaluator import evaluate_strategy
from app.signals.dsl.market_ctx import MarketCtx
from app.signals.dsl.schema import StrategyDef
from app.signals.schema import Signal


def _df_from_klines(klines: list[dict]) -> pd.DataFrame:
    if not klines:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(klines)
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def evaluate(
    symbol: str,
    tf_klines: dict[str, list[dict]],
    *,
    strategy: StrategyDef,
    news: list[dict] | None = None,
    blackout: bool = False,
    fear_greed: float | None = None,
    reddit_hype: float | None = None,
    now: datetime | None = None,
) -> Signal | None:
    klines = {tf: _df_from_klines(rows) for tf, rows in tf_klines.items()}
    ctx = MarketCtx(
        symbol=symbol,
        klines=klines,
        news=news or [],
        blackout=blackout,
        fear_greed=fear_greed,
        reddit_hype=reddit_hype,
        now=now or datetime.now(timezone.utc),
    )
    return evaluate_strategy(strategy, ctx)
