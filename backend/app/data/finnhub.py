"""Finnhub news + sentiment client."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

import httpx

from app.config import get_settings

log = logging.getLogger("finnhub")
BASE = "https://finnhub.io/api/v1"


async def fetch_crypto_news() -> list[dict]:
    s = get_settings()
    if not s.FINNHUB_API_KEY:
        return []
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{BASE}/news",
            params={"category": "crypto", "token": s.FINNHUB_API_KEY},
        )
        r.raise_for_status()
        rows = r.json()
    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "source": "finnhub",
                "external_id": str(row.get("id")),
                "headline": row.get("headline") or "",
                "url": row.get("url") or "",
                "symbols": _extract_symbols(row.get("related") or "", row.get("headline") or ""),
                "sentiment": _crude_sentiment(row.get("headline") or ""),
                "published_at": datetime.fromtimestamp(int(row.get("datetime") or 0), tz=timezone.utc),
            }
        )
    return out


def _extract_symbols(related: str, headline: str) -> list[str]:
    syms = set()
    for tok in related.replace(",", " ").split():
        tok = tok.upper().strip()
        if tok in {"BTC", "ETH", "SOL", "XRP", "BNB"}:
            syms.add(tok + "USDT")
    upper = headline.upper()
    for k, v in {"BITCOIN": "BTCUSDT", "ETHEREUM": "ETHUSDT"}.items():
        if k in upper:
            syms.add(v)
    return sorted(syms)


_BULL = ("surge", "rally", "soar", "approve", "approved", "breakout", "all-time", "bullish", "adopt")
_BEAR = ("crash", "plunge", "ban", "hack", "exploit", "lawsuit", "bearish", "reject", "decline")


def _crude_sentiment(headline: str) -> float:
    h = headline.lower()
    score = 0.0
    for w in _BULL:
        if w in h:
            score += 0.4
    for w in _BEAR:
        if w in h:
            score -= 0.4
    return max(-1.0, min(1.0, score))
