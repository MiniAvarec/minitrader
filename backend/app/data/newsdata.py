"""NewsData.io crypto news client — mainstream business news mentioning crypto.

Free tier is 200 credits/day. We poll on a slow cadence (gated to every Nth
news loop in news_worker.py) so daily usage stays well under that cap.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.data._sentiment import crude_sentiment
from app.data._symbols import extract_symbols
from app.settings_store import get_setting

log = logging.getLogger("newsdata")
BASE = "https://newsdata.io/api/1"


async def fetch_news() -> list[dict]:
    api_key = await get_setting("newsdata_api_key")
    if not api_key:
        return []
    params = {
        "apikey": api_key,
        "category": "business",
        "q": "bitcoin OR ethereum OR crypto OR cryptocurrency",
        "language": "en",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{BASE}/latest", params=params)
            r.raise_for_status()
            payload = r.json()
    except httpx.HTTPError as e:
        log.warning("newsdata fetch failed: %s", e)
        return []

    rows = payload.get("results") or []
    out: list[dict] = []
    for row in rows:
        title = row.get("title") or ""
        description = row.get("description") or ""
        url = row.get("link") or ""
        published_raw = row.get("pubDate") or ""
        try:
            # NewsData returns "YYYY-MM-DD HH:MM:SS" in UTC.
            published_at = datetime.strptime(published_raw, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            published_at = datetime.now(timezone.utc)
        out.append(
            {
                "source": "newsdata",
                "external_id": str(row.get("article_id") or url or title)[:128],
                "headline": title,
                "url": url,
                "symbols": extract_symbols(title, description),
                "sentiment": crude_sentiment(f"{title}. {description}"),
                "published_at": published_at,
            }
        )
    return out
