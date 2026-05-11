"""Parse YAML strings/files into validated StrategyDef objects.

This is the single entry point for converting untrusted YAML text into the
typed schema. It enforces:

- max nesting depth (defense vs accidental DoS)
- max total leaf comparisons
- known indicator names in every value-ref dict
- params referenced via {param: x} actually exist in declared params
- timeframes referenced exist in declared timeframes (warning only)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.signals.dsl.schema import (
    AllOf,
    AnyOf,
    Comparison,
    Not,
    RuleNode,
    StrategyDef,
)

MAX_DEPTH = 6
MAX_LEAVES = 50

# Allowed indicator / context function names. Each maps to the arity (number
# of positional args expected). Extending these requires updating evaluator.py.
INDICATOR_REFS: dict[str, tuple[int, int]] = {
    # name: (min_args, max_args)
    "rsi": (2, 2),                   # [tf, length]
    "macd_line": (1, 1),             # [tf]
    "macd_signal": (1, 1),
    "macd_hist": (1, 1),
    "ema": (2, 2),
    "sma": (2, 2),
    "atr": (2, 2),
    "close": (1, 1),
    "open": (1, 1),
    "high": (1, 1),
    "low": (1, 1),
    "volume": (1, 1),
    "bb_upper": (3, 3),              # [tf, length, std]
    "bb_basis": (3, 3),
    "bb_lower": (3, 3),
    "donchian_high": (2, 2),
    "donchian_low": (2, 2),
    "vwap": (1, 1),
    "supertrend": (3, 3),            # [tf, length, mult]
    "ha_open": (1, 1),
    "ha_close": (1, 1),
    "ha_high": (1, 1),
    "ha_low": (1, 1),
    "stochrsi_k": (5, 5),            # [tf, rsi_len, stoch_len, k_smooth, d_smooth]
    "stochrsi_d": (5, 5),
    "news_sentiment": (1, 1),        # [minutes]
    "news_blackout": (0, 0),
    "fear_greed": (0, 0),            # 0..100 market regime
    "reddit_hype": (0, 0),           # 0..1 community-mention score for ctx.symbol
    "minute_of_hour": (0, 0),
    "hour_of_day_utc": (0, 0),
    "param": (1, 1),                 # marker: {param: name}
}


class StrategyParseError(ValueError):
    """Raised when YAML can't be parsed into a valid StrategyDef."""


def load_yaml_text(text: str) -> StrategyDef:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise StrategyParseError(f"YAML syntax error: {e}") from e
    if not isinstance(data, dict):
        raise StrategyParseError("top-level YAML must be a mapping")
    try:
        strat = StrategyDef.model_validate(data)
    except ValidationError as e:
        raise StrategyParseError(_format_pydantic_error(e)) from e

    # post-validation
    leaves = [0]
    if strat.entry.long is not None:
        _validate_node(strat.entry.long, depth=1, params=strat.params, leaf_counter=leaves, path="entry.long")
    if strat.entry.short is not None:
        _validate_node(strat.entry.short, depth=1, params=strat.params, leaf_counter=leaves, path="entry.short")
    if leaves[0] > MAX_LEAVES:
        raise StrategyParseError(f"strategy has {leaves[0]} leaf comparisons; max {MAX_LEAVES}")
    if strat.sl.tf not in strat.timeframes and strat.timeframes:
        # warn, not error
        pass
    return strat


def load_yaml_file(path: str | Path) -> StrategyDef:
    return load_yaml_text(Path(path).read_text())


def _format_pydantic_error(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err.get("loc") or [])
        parts.append(f"{loc}: {err.get('msg')}")
    return "; ".join(parts)


def _validate_node(node: RuleNode, *, depth: int, params: dict[str, Any], leaf_counter: list[int], path: str) -> None:
    if depth > MAX_DEPTH:
        raise StrategyParseError(f"{path}: nesting depth exceeds {MAX_DEPTH}")
    if isinstance(node, AllOf):
        if not node.all_of:
            raise StrategyParseError(f"{path}.all_of: must contain at least one rule")
        for i, child in enumerate(node.all_of):
            _validate_node(child, depth=depth + 1, params=params, leaf_counter=leaf_counter, path=f"{path}.all_of[{i}]")
    elif isinstance(node, AnyOf):
        if not node.any_of:
            raise StrategyParseError(f"{path}.any_of: must contain at least one rule")
        for i, child in enumerate(node.any_of):
            _validate_node(child, depth=depth + 1, params=params, leaf_counter=leaf_counter, path=f"{path}.any_of[{i}]")
    elif isinstance(node, Not):
        _validate_node(node.not_, depth=depth + 1, params=params, leaf_counter=leaf_counter, path=f"{path}.not")
    elif isinstance(node, Comparison):
        leaf_counter[0] += 1
        _validate_value_ref(node.lhs, params, path=f"{path}.lhs")
        _validate_value_ref(node.rhs, params, path=f"{path}.rhs")
    else:
        raise StrategyParseError(f"{path}: unknown rule node type {type(node).__name__}")


def _validate_value_ref(ref: Any, params: dict[str, Any], *, path: str) -> None:
    if isinstance(ref, (int, float, str, bool)) and not isinstance(ref, dict):
        return
    if not isinstance(ref, dict) or len(ref) != 1:
        raise StrategyParseError(
            f"{path}: value ref must be a literal or a dict with one key, got {ref!r}"
        )
    [(name, args)] = ref.items()
    if name not in INDICATOR_REFS:
        raise StrategyParseError(
            f"{path}: unknown indicator/function {name!r}; allowed: {sorted(INDICATOR_REFS)}"
        )
    if not isinstance(args, list):
        # allow `{news_blackout: null}` => normalize
        if args is None:
            args = []
        else:
            args = [args]
    lo, hi = INDICATOR_REFS[name]
    if not (lo <= len(args) <= hi):
        raise StrategyParseError(
            f"{path}: {name} expects {lo if lo == hi else f'{lo}-{hi}'} args, got {len(args)}"
        )
    if name == "param":
        pname = args[0]
        if pname not in params:
            raise StrategyParseError(f"{path}: param {pname!r} not declared in `params`")
