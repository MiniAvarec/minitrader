"""Macro economic calendar (high-impact events).

Uses ForexFactory's public weekly JSON. No API key required.
We treat the next 15 minutes after a high-impact event as a 'window' during
which signal generation is suppressed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

log = logging.getLogger("calendar")
URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


async def fetch_high_impact() -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(URL)
            r.raise_for_status()
            rows = r.json()
        except Exception as e:
            log.warning("calendar fetch failed: %s", e)
            return []
    out: list[dict] = []
    for row in rows:
        impact = (row.get("impact") or "").lower()
        if impact != "high":
            continue
        when = _parse_iso(row.get("date"))
        if when is None:
            continue
        out.append(
            {
                "title": row.get("title"),
                "country": row.get("country"),
                "when": when.isoformat(),
            }
        )
    return out


def _parse_iso(s: Optional[str]) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def is_in_blackout(events: list[dict], now: datetime, window_min: int = 15) -> bool:
    """True if `now` is within ±window of any high-impact event."""
    for e in events:
        when = _parse_iso(e.get("when"))
        if when is None:
            continue
        if abs((when - now).total_seconds()) <= window_min * 60:
            return True
    return False
