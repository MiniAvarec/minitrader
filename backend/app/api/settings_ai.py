"""Per-user AI evaluation settings (OpenRouter key + 3 model choices)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.catalog import (
    ensure_in_list,
    get_available_models,
    pick_default_models,
)
from app.ai.openrouter import ping
from app.auth.deps import current_user
from app.db.models import User, UserAISettings
from app.db.session import get_db
from app.keys.crypto import decrypt, encrypt
from app.security import limiter


router = APIRouter(prefix="/settings/ai", tags=["settings", "ai"])


class AISettingsIn(BaseModel):
    openrouter_api_key: str | None = Field(default=None)
    model_a: str | None = None
    model_b: str | None = None
    model_c: str | None = None


async def _get_or_create(db: AsyncSession, user_id: int) -> UserAISettings:
    row = (
        await db.execute(select(UserAISettings).where(UserAISettings.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        # First-time row — seed with the freshest top-3 frontier models we can
        # see right now. If the catalog is unreachable we fall through to the
        # static defaults inside pick_default_models.
        a, b, c = await pick_default_models()
        row = UserAISettings(user_id=user_id, model_a=a, model_b=b, model_c=c)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def _validate_model_id(model_id: str) -> None:
    """Light validation only — the live OpenRouter catalog changes too fast
    to maintain a strict whitelist server-side. We just sanity-check format
    and let OpenRouter reject unknown IDs at eval time with a clean error."""
    if not isinstance(model_id, str):
        raise HTTPException(400, "model id must be a string")
    mid = model_id.strip()
    if not mid or "/" not in mid or len(mid) > 128:
        raise HTTPException(400, f"invalid model id: {model_id!r}")


@router.get("")
async def get_ai_settings(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_or_create(db, user.id)
    available = await get_available_models()
    # Make sure each saved model is selectable in the dropdown even if it has
    # since rotated out of OpenRouter's catalog.
    for mid in (row.model_a, row.model_b, row.model_c):
        available = ensure_in_list(available, mid)
    return {
        "has_key": row.encrypted_openrouter_key is not None,
        "model_a": row.model_a,
        "model_b": row.model_b,
        "model_c": row.model_c,
        "available_models": available,
    }


@router.put("")
async def put_ai_settings(
    body: AISettingsIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_or_create(db, user.id)
    if body.openrouter_api_key is not None:
        if body.openrouter_api_key.strip() == "":
            row.encrypted_openrouter_key = None
        else:
            row.encrypted_openrouter_key = encrypt(body.openrouter_api_key.strip())
    if body.model_a:
        _validate_model_id(body.model_a)
        row.model_a = body.model_a.strip()
    if body.model_b:
        _validate_model_id(body.model_b)
        row.model_b = body.model_b.strip()
    if body.model_c:
        _validate_model_id(body.model_c)
        row.model_c = body.model_c.strip()
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "ok": True,
        "has_key": row.encrypted_openrouter_key is not None,
        "model_a": row.model_a,
        "model_b": row.model_b,
        "model_c": row.model_c,
    }


@router.post("/test")
@limiter.limit("10/minute")
async def test_ai_settings(
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_or_create(db, user.id)
    if row.encrypted_openrouter_key is None:
        raise HTTPException(400, "no OpenRouter key saved")
    try:
        key = decrypt(row.encrypted_openrouter_key)
    except Exception:
        raise HTTPException(500, "failed to decrypt stored key — re-enter it")
    ok, detail = await ping(key, row.model_a)
    return {"ok": ok, "detail": detail, "model": row.model_a}


@router.post("/refresh-catalog")
@limiter.limit("5/minute")
async def refresh_catalog(
    request: Request,
    user: User = Depends(current_user),
):
    """Force a re-fetch of the OpenRouter model catalog (skips the 1h cache)."""
    models = await get_available_models(force=True)
    return {"count": len(models), "models": models}
