"""Reddit community hype client — counts and weights symbol mentions across
the major crypto subs. No API key required; uses the public JSON endpoints.

Output: { "BTCUSDT": {"score": 0.83, "mentions_60m": 42, "upvotes_60m": 5120}, ... }

The score is normalised to 0..1 across all symbols seen in the current poll
so strategies can use absolute thresholds (e.g. > 0.7 = "this coin is on fire
right now"). Symbols not mentioned at all are simply absent.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import httpx

from app.data._symbols import TRACKED_BASES, to_perp
from app.settings_store import get_setting

log = logging.getLogger("reddit_hype")

SUBS = ("CryptoCurrency", "Bitcoin", "ethereum", "CryptoMarkets")
WINDOW_SECONDS = 60 * 60  # 60-minute lookback


def _word_present(base: str, text: str) -> bool:
    """Cheap word-boundary check without compiling per call."""
    if not text:
        return False
    upper = text.upper()
    i = 0
    n = len(upper)
    target = base
    tlen = len(target)
    while True:
        i = upper.find(target, i)
        if i < 0:
            return False
        before = upper[i - 1] if i > 0 else " "
        after = upper[i + tlen] if i + tlen < n else " "
        if not before.isalnum() and not after.isalnum():
            return True
        i += tlen


async def fetch_hype() -> dict[str, dict]:
    user_agent = await get_setting("reddit_user_agent") or "minitrader/0.1"
    headers = {"User-Agent": user_agent}
    cutoff = datetime.now(timezone.utc).timestamp() - WINDOW_SECONDS

    # base -> (mentions, upvotes, comments)
    agg: dict[str, list[int]] = {b: [0, 0, 0] for b in TRACKED_BASES}

    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        for sub in SUBS:
            try:
                r = await client.get(
                    f"https://www.reddit.com/r/{sub}/new.json",
                    params={"limit": 50},
                )
                r.raise_for_status()
                payload = r.json()
            except httpx.HTTPError as e:
                log.warning("reddit r/%s fetch failed: %s", sub, e)
                continue
            children = (payload.get("data") or {}).get("children") or []
            for child in children:
                post = (child or {}).get("data") or {}
                created = float(post.get("created_utc") or 0.0)
                if created < cutoff:
                    continue
                score = int(post.get("score") or 0)
                comments = int(post.get("num_comments") or 0)
                blob = f"{post.get('title') or ''} {post.get('selftext') or ''}"
                for base in TRACKED_BASES:
                    if _word_present(base, blob):
                        a = agg[base]
                        a[0] += 1
                        a[1] += max(score, 0)
                        a[2] += comments

    # Compose a raw heat per symbol: mentions weighted by sqrt(upvotes+comments)
    # so a single viral post doesn't dominate a real community trend.
    raw: dict[str, float] = {}
    for base, (mentions, upvotes, comments) in agg.items():
        if mentions == 0:
            continue
        raw[base] = mentions * math.sqrt(1 + upvotes + comments)

    if not raw:
        return {}
    peak = max(raw.values())
    fetched_at = datetime.now(timezone.utc)
    out: dict[str, dict] = {}
    for base, heat in raw.items():
        mentions, upvotes, _ = agg[base]
        out[to_perp(base)] = {
            "score": heat / peak if peak > 0 else 0.0,
            "mentions_60m": mentions,
            "upvotes_60m": upvotes,
            "fetched_at": fetched_at,
        }
    return out
