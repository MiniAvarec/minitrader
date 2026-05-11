"""Pydantic schema for the strategy YAML DSL.

Top-level shape:

    name: str
    description: str
    timeframes: [str]
    cooldown_min: int = 10
    params: { name: number_or_string }
    entry:
      long:  RuleNode
      short: RuleNode (optional)
    sl: SLTPDef
    tp: SLTPDef
    news_modifier:
      allow_veto: bool
      allow_boost: bool

A RuleNode is one of:
  - { all_of: [RuleNode, ...] }
  - { any_of: [RuleNode, ...] }
  - { not:    RuleNode }
  - { lhs: ValueRef, op: str, rhs: ValueRef }     -- a comparison

A ValueRef is one of:
  - a literal number/string/bool
  - { param: name }
  - { rsi: [tf, length] }
  - { macd_hist: [tf] }   (also: macd_line, macd_signal)
  - { ema: [tf, length] } (also: sma)
  - { atr: [tf, length] }
  - { close|open|high|low|volume: [tf] }
  - { bb_upper|bb_basis|bb_lower: [tf, length, std] }
  - { donchian_high|donchian_low: [tf, length] }
  - { vwap: [tf] }
  - { supertrend: [tf, length, mult] }   -- +1 / -1
  - { ha_open|ha_close|ha_high|ha_low: [tf] }
  - { stochrsi_k|stochrsi_d: [tf, rsi_len, stoch_len, k_smooth, d_smooth] }
  - { news_sentiment: [minutes] }
  - { news_blackout: [] }
  - { fear_greed: [] }       -- Crypto Fear & Greed Index, 0..100
  - { reddit_hype: [] }      -- Reddit community-mention score for ctx.symbol, 0..1
  - { minute_of_hour: [] }
  - { hour_of_day_utc: [] }
"""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field, model_validator


# Kept simple on purpose: ValueRef is a Python primitive OR a dict with a single key
# whose name identifies the function. We don't model every shape with a discriminated
# union — that would explode the schema. Validation lives in loader.py.
ValueRef = Union[int, float, str, bool, dict]

OP_LITERALS = {"<", ">", "<=", ">=", "==", "!=", "crosses_above", "crosses_below"}


class Comparison(BaseModel):
    lhs: ValueRef
    op: str
    rhs: ValueRef

    @model_validator(mode="after")
    def _check_op(self) -> "Comparison":
        if self.op not in OP_LITERALS:
            raise ValueError(f"unknown op {self.op!r}; allowed: {sorted(OP_LITERALS)}")
        return self


class AllOf(BaseModel):
    all_of: list["RuleNode"]


class AnyOf(BaseModel):
    any_of: list["RuleNode"]


class Not(BaseModel):
    not_: "RuleNode" = Field(alias="not")

    model_config = {"populate_by_name": True}


RuleNode = Union[AllOf, AnyOf, Not, Comparison]


class EntryDef(BaseModel):
    long: RuleNode | None = None
    short: RuleNode | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "EntryDef":
        if self.long is None and self.short is None:
            raise ValueError("entry must define at least one of `long` or `short`")
        return self


class SLTPDef(BaseModel):
    """Either ATR-based (atr_mult on a given tf) or a fixed % move."""
    atr_mult: float | None = None
    atr_length: int = 14
    pct: float | None = None  # e.g. 0.005 for 0.5% — alternative to atr_mult
    tf: str = "15m"

    @model_validator(mode="after")
    def _exactly_one(self) -> "SLTPDef":
        if (self.atr_mult is None) == (self.pct is None):
            raise ValueError("SL/TP must specify exactly one of `atr_mult` or `pct`")
        return self


class NewsModifier(BaseModel):
    allow_veto: bool = True
    allow_boost: bool = True


class StrategyDef(BaseModel):
    name: str
    description: str = ""
    timeframes: list[str] = Field(default_factory=list)
    cooldown_min: int = 10
    params: dict[str, Any] = Field(default_factory=dict)
    entry: EntryDef
    sl: SLTPDef
    tp: SLTPDef
    news_modifier: NewsModifier = Field(default_factory=NewsModifier)


# Resolve forward refs
AllOf.model_rebuild()
AnyOf.model_rebuild()
Not.model_rebuild()
EntryDef.model_rebuild()
StrategyDef.model_rebuild()
