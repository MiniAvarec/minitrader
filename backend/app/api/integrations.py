"""System-wide integration settings (news/sentiment API keys etc.)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException

from app.auth.deps import current_user
from app.db.models import User
from app.settings_store import (
    INTEGRATIONS,
    delete_setting,
    integration,
    set_setting,
    status,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("")
async def list_integrations(user: User = Depends(current_user)) -> list[dict]:
    return [await status(spec.slug) for spec in INTEGRATIONS]


@router.put("/{slug}")
async def upsert_integration(
    slug: str,
    body: dict = Body(...),
    user: User = Depends(current_user),
) -> dict:
    try:
        integration(slug)
    except KeyError:
        raise HTTPException(404, f"unknown integration {slug!r}")
    value = (body.get("value") or "").strip()
    if not value:
        raise HTTPException(400, "value is required (use DELETE to clear)")
    await set_setting(slug, value)
    return await status(slug)


@router.delete("/{slug}")
async def delete_integration(
    slug: str, user: User = Depends(current_user)
) -> dict:
    try:
        integration(slug)
    except KeyError:
        raise HTTPException(404, f"unknown integration {slug!r}")
    await delete_setting(slug)
    return await status(slug)


@router.post("/{slug}/test")
async def test_integration(
    slug: str,
    body: dict = Body(...),
    user: User = Depends(current_user),
) -> dict:
    """Round-trip the provided value against the upstream API.

    Accepts the proposed value in the body so the UI can verify a key before
    saving it. Returns {ok: true, detail: "..."} on success; raises 400 with
    the upstream error message on failure.
    """
    try:
        spec = integration(slug)
    except KeyError:
        raise HTTPException(404, f"unknown integration {slug!r}")
    value = (body.get("value") or "").strip()
    if not value:
        raise HTTPException(400, "value is required")
    try:
        detail = await _probe(spec.slug, value)
    except _ProbeError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "detail": detail}


class _ProbeError(Exception):
    pass


async def _probe(slug: str, value: str) -> str:
    """Make one low-cost upstream request to confirm the key works.

    Each integration uses its own minimal probe endpoint. Returns a short
    human-readable string on success; raises _ProbeError on failure.
    """
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if slug == "finnhub_api_key":
            r = await client.get(
                "https://finnhub.io/api/v1/news",
                params={"category": "crypto", "token": value},
            )
            if r.status_code == 401:
                raise _ProbeError("Finnhub rejected the key (401).")
            r.raise_for_status()
            items = r.json() if r.headers.get("content-type", "").startswith("application/json") else []
            return f"Finnhub OK · {len(items)} headlines available"

        if slug == "cryptopanic_api_key":
            r = await client.get(
                "https://cryptopanic.com/api/v1/posts/",
                params={"auth_token": value, "public": "true", "kind": "news"},
            )
            if r.status_code in (401, 403):
                raise _ProbeError("CryptoPanic rejected the token.")
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("status") == "Incomplete":
                raise _ProbeError(data.get("info") or "CryptoPanic returned an error.")
            count = len((data or {}).get("results") or [])
            return f"CryptoPanic OK · {count} headlines available"

        if slug == "cryptocompare_api_key":
            r = await client.get(
                "https://min-api.cryptocompare.com/data/v2/news/",
                params={"lang": "EN", "api_key": value},
            )
            r.raise_for_status()
            data = r.json()
            if (data or {}).get("Response") == "Error":
                raise _ProbeError(data.get("Message") or "CryptoCompare rejected the key.")
            count = len((data or {}).get("Data") or [])
            return f"CryptoCompare OK · {count} headlines available"

        if slug == "newsdata_api_key":
            r = await client.get(
                "https://newsdata.io/api/1/latest",
                params={"apikey": value, "category": "business", "language": "en"},
            )
            if r.status_code in (401, 403):
                raise _ProbeError("NewsData.io rejected the key.")
            r.raise_for_status()
            data = r.json()
            if (data or {}).get("status") == "error":
                raise _ProbeError(((data.get("results") or {}).get("message")) or "NewsData.io error.")
            count = len((data or {}).get("results") or [])
            return f"NewsData.io OK · {count} headlines available"

        if slug == "reddit_user_agent":
            r = await client.get(
                "https://www.reddit.com/r/CryptoCurrency/hot.json",
                params={"limit": 1},
                headers={"User-Agent": value},
            )
            if r.status_code == 429:
                raise _ProbeError("Reddit rate-limited the request — try a different UA.")
            r.raise_for_status()
            payload = r.json()
            n = len(((payload or {}).get("data") or {}).get("children") or [])
            return f"Reddit OK · received {n} post(s) with this UA"

    raise _ProbeError(f"no probe defined for {slug!r}")
