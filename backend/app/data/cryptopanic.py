"""CryptoPanic news client."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.config import get_settings

log = logging.getLogger("cryptopanic")
BASE = "https://cryptopanic.com/api/v1"


async def fetch_news() -> list[dict]:
    s = get_settings()
    if not s.CRYPTOPANIC_API_KEY:
        return []
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{BASE}/posts/",
            params={"auth_token": s.CRYPTOPANIC_API_KEY, "kind": "news", "public": "true"},
        )
        r.raise_for_status()
        data = r.json()
    out: list[dict] = []
    for row in data.get("results", []):
        votes = row.get("votes") or {}
        sentiment = _votes_to_sentiment(votes)
        symbols = []
        for c in row.get("currencies") or []:
            code = (c.get("code") or "").upper()
            if code in {"BTC", "ETH", "SOL", "XRP", "BNB"}:
                symbols.append(code + "USDT")
        out.append(
            {
                "source": "cryptopanic",
                "external_id": str(row.get("id")),
                "headline": row.get("title") or "",
                "url": row.get("url") or "",
                "symbols": sorted(set(symbols)),
                "sentiment": sentiment,
                "published_at": _parse_dt(row.get("published_at")),
            }
        )
    return out


def _votes_to_sentiment(v: dict) -> float:
    pos = (v.get("positive") or 0) + (v.get("important") or 0)
    neg = (v.get("negative") or 0) + (v.get("toxic") or 0)
    total = pos + neg
    if not total:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / total))


def _parse_dt(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)
