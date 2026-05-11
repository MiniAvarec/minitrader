"""GDELT 2.0 DocAPI client — global news with tone, free and key-less.

Filters for crypto-relevant articles using a theme + keyword OR. Returns the
last ~75 articles per poll. Tone is normalised from GDELT's typical [-10, +10]
range into our [-1, +1] sentiment convention.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.data._sentiment import crude_sentiment
from app.data._symbols import extract_symbols

log = logging.getLogger("gdelt")
BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

# Query: any of the major coin names OR a crypto theme tag. The full-text
# search OR-combines bare keywords automatically.
_QUERY = (
    '(bitcoin OR ethereum OR crypto OR cryptocurrency OR ripple OR solana) '
    'sourcelang:english'
)


async def fetch_news() -> list[dict]:
    params = {
        "query": _QUERY,
        "mode": "ArtList",
        "format": "JSON",
        "timespan": "30min",
        "maxrecords": "75",
        "sort": "DateDesc",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(BASE, params=params)
            r.raise_for_status()
            # GDELT occasionally returns text/html on transient errors.
            ctype = r.headers.get("content-type", "")
            if "json" not in ctype:
                log.warning("gdelt non-json response: %s", ctype)
                return []
            payload = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("gdelt fetch failed: %s", e)
        return []

    rows = payload.get("articles") or []
    out: list[dict] = []
    for row in rows:
        title = row.get("title") or ""
        url = row.get("url") or ""
        seen = row.get("seendate") or ""  # "YYYYMMDDTHHMMSSZ"
        try:
            published_at = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            published_at = datetime.now(timezone.utc)

        # `tone` is a free-text field on the DocAPI; not always present. Fall
        # back to the title-keyword lexicon when missing or near-zero.
        tone_raw = row.get("tone")
        sentiment = _normalise_tone(tone_raw)
        if abs(sentiment) < 0.05:
            sentiment = crude_sentiment(title)

        out.append(
            {
                "source": "gdelt",
                "external_id": url[:128] or title[:128],
                "headline": title,
                "url": url,
                "symbols": extract_symbols(title),
                "sentiment": sentiment,
                "published_at": published_at,
            }
        )
    return out


def _normalise_tone(raw) -> float:
    """GDELT tone ranges roughly -10..+10 in practice. Map linearly to -1..1."""
    if raw is None:
        return 0.0
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(-1.0, min(1.0, v / 10.0))
