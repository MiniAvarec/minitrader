"""Tiny keyword-based sentiment scorer shared across news sources.

Used by sources that don't carry their own sentiment signal (Finnhub headlines,
GDELT tone-tie-breakers, NewsData.io, CryptoCompare when upvotes are absent).
CryptoPanic has its own votes-based scorer and doesn't use this.
"""
from __future__ import annotations


_BULL = (
    "surge", "rally", "soar", "approve", "approved", "breakout", "all-time",
    "bullish", "adopt", "adoption", "upgrade", "partnership", "etf",
    "institutional", "buy", "accumulate",
)
_BEAR = (
    "crash", "plunge", "ban", "hack", "exploit", "lawsuit", "bearish",
    "reject", "decline", "selloff", "liquidation", "fraud", "sec sues",
    "delist", "outage", "rugpull", "rug pull",
)


def crude_sentiment(headline: str) -> float:
    """Return a -1..1 score from keyword presence. Saturates at the bounds."""
    h = (headline or "").lower()
    score = 0.0
    for w in _BULL:
        if w in h:
            score += 0.4
    for w in _BEAR:
        if w in h:
            score -= 0.4
    return max(-1.0, min(1.0, score))
