"""Finnhub news + sentiment client."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.data._sentiment import crude_sentiment
from app.data._symbols import extract_symbols
from app.settings_store import get_setting

log = logging.getLogger("finnhub")
BASE = "https://finnhub.io/api/v1"


async def fetch_crypto_news() -> list[dict]:
    api_key = await get_setting("finnhub_api_key")
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{BASE}/news",
            params={"category": "crypto", "token": api_key},
        )
        r.raise_for_status()
        rows = r.json()
    out: list[dict] = []
    for row in rows:
        headline = row.get("headline") or ""
        out.append(
            {
                "source": "finnhub",
                "external_id": str(row.get("id")),
                "headline": headline,
                "url": row.get("url") or "",
                "symbols": extract_symbols(row.get("related") or "", headline),
                "sentiment": crude_sentiment(headline),
                "published_at": datetime.fromtimestamp(int(row.get("datetime") or 0), tz=timezone.utc),
            }
        )
    return out
