from __future__ import annotations

from itertools import product
from typing import Any

from app.backtest.runner import BacktestResult, run as backtest_run
from app.signals.dsl.schema import StrategyDef


def expand_grid(grid: dict[str, list[Any]], *, max_candidates: int = 64) -> list[dict[str, Any]]:
    if not grid:
        return [{}]
    keys = list(grid)
    values = [grid[k] for k in keys]
    rows = [dict(zip(keys, combo)) for combo in product(*values)]
    return rows[:max_candidates]


async def optimize(
    strategy: StrategyDef,
    exchange: str,
    symbol: str,
    *,
    param_grid: dict[str, list[Any]],
    train_hours: int = 168,
    validation_hours: int = 72,
    notional_usdt: float = 100.0,
    max_candidates: int = 64,
) -> dict:
    candidates = expand_grid(param_grid, max_candidates=max_candidates)
    ranked: list[dict] = []
    full_hours = max(24, train_hours + validation_hours)
    validation_hours = max(6, validation_hours)
    for params in candidates:
        candidate = strategy.model_copy(deep=True)
        candidate.params = {**candidate.params, **params}
        train_result = await backtest_run(
            candidate, exchange, symbol, hours=full_hours, notional_usdt=notional_usdt
        )
        validation_result = await backtest_run(
            candidate, exchange, symbol, hours=validation_hours, notional_usdt=notional_usdt
        )
        ranked.append(_score(params, train_result, validation_result))
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return {
        "exchange": exchange,
        "symbol": symbol,
        "candidates": ranked,
        "best": ranked[0] if ranked else None,
    }


def _score(params: dict[str, Any], train: BacktestResult, validation: BacktestResult) -> dict:
    train_pnl = train.total_pnl_pct
    val_pnl = validation.total_pnl_pct
    stability = 1.0 - min(1.0, abs(train_pnl - val_pnl))
    drawdown_penalty = validation.max_drawdown_pct
    score = val_pnl + validation.win_rate * 0.25 + stability * 0.25 - drawdown_penalty * 0.75
    return {
        "params": params,
        "score": score,
        "stability": stability,
        "train": _summary(train),
        "validation": _summary(validation),
    }


def _summary(result: BacktestResult) -> dict:
    return {
        "trades": len(result.trades),
        "win_rate": result.win_rate,
        "total_pnl_usdt": result.total_pnl_usdt,
        "total_pnl_pct": result.total_pnl_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
    }
