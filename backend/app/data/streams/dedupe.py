"""Kline de-dup + gap detector.

Two redundant WS sources push bars into one queue. The de-dup buffer keeps the
last `open_time` we've successfully published per (exchange, symbol, tf) so the
consumer can classify each incoming bar:

  - "first": new bar, publish it.
  - "duplicate": same open_time as last_closed → drop (or update last open).
  - "gap": open_time is more than one tf-interval after the last → fetch the
    missing range via REST before publishing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Verdict = Literal["first", "duplicate", "gap"]


def tf_to_ms(tf: str) -> int:
    n = int(tf[:-1])
    u = tf[-1]
    return n * {"s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}[u]


@dataclass
class KlineDedupeBuffer:
    """Per-(exchange, symbol, tf) last-seen open_time + gap detection."""

    last_open: dict[tuple[str, str, str], int] = field(default_factory=dict)

    def classify(self, exchange: str, symbol: str, tf: str, open_time: int) -> Verdict:
        key = (exchange, symbol, tf)
        prev = self.last_open.get(key)
        if prev is None:
            return "first"
        if open_time == prev:
            return "duplicate"
        if open_time < prev:
            return "duplicate"
        step = tf_to_ms(tf)
        if open_time - prev > step:
            return "gap"
        return "first"

    def gap_range(self, exchange: str, symbol: str, tf: str, open_time: int) -> tuple[int, int]:
        """Return (start_ms_exclusive, end_ms_exclusive) of bars that need REST backfill."""
        prev = self.last_open[(exchange, symbol, tf)]
        step = tf_to_ms(tf)
        return (prev + step, open_time)

    def record(self, exchange: str, symbol: str, tf: str, open_time: int) -> None:
        self.last_open[(exchange, symbol, tf)] = open_time
