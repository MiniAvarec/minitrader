"""Alternative.me Crypto Fear & Greed Index — free, no key required.

Returns the latest 0..100 score plus its qualitative classification. Strategies
consume this via the `fear_greed[]` DSL term as a market-regime filter.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

log = logging.getLogger("feargreed")
URL = "https://api.alternative.me/fng/"


async def fetch_index() -> dict | None:
    """Return {value: float, classification: str, fetched_at: datetime} or None."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(URL, params={"limit": 1})
            r.raise_for_status()
            payload = r.json()
    except httpx.HTTPError as e:
        log.warning("feargreed fetch failed: %s", e)
        return None

    rows = payload.get("data") or []
    if not rows:
        return None
    row = rows[0]
    try:
        value = float(row.get("value"))
    except (TypeError, ValueError):
        return None
    classification = row.get("value_classification") or ""
    return {
        "value": value,
        "classification": classification,
        "fetched_at": datetime.now(timezone.utc),
    }
