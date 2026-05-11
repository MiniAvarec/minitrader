"""CryptoCompare (CCData) news client — aggregates ~150 crypto sources."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.data._sentiment import crude_sentiment
from app.data._symbols import code_to_perp, extract_symbols
from app.settings_store import get_setting

log = logging.getLogger("cryptocompare")
BASE = "https://min-api.cryptocompare.com/data/v2"


async def fetch_news() -> list[dict]:
    api_key = await get_setting("cryptocompare_api_key")
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{BASE}/news/",
            params={"lang": "EN", "api_key": api_key},
        )
        r.raise_for_status()
        payload = r.json()
    rows = payload.get("Data") or []
    out: list[dict] = []
    for row in rows:
        title = row.get("title") or ""
        body = row.get("body") or ""
        # CryptoCompare returns a comma-separated `categories` field; map known
        # codes (BTC, ETH, …) to perps. Anything else goes through the generic
        # headline scanner.
        cat_symbols: list[str] = []
        for cat in (row.get("categories") or "").split("|"):
            perp = code_to_perp(cat)
            if perp:
                cat_symbols.append(perp)
        symbols = sorted(set(cat_symbols) | set(extract_symbols(title, body)))
        # CC publishes the raw post; no per-article sentiment, so fall back to
        # our keyword lexicon over title+body for richer context than title alone.
        sentiment = crude_sentiment(f"{title}. {body}")
        published_ts = row.get("published_on")
        try:
            published_at = datetime.fromtimestamp(int(published_ts or 0), tz=timezone.utc)
        except (TypeError, ValueError):
            published_at = datetime.now(timezone.utc)
        out.append(
            {
                "source": "cryptocompare",
                "external_id": str(row.get("id") or row.get("guid") or row.get("url") or title)[:128],
                "headline": title,
                "url": row.get("url") or "",
                "symbols": symbols,
                "sentiment": sentiment,
                "published_at": published_at,
            }
        )
    return out
