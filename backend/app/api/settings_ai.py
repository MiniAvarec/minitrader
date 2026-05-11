"""Per-user AI evaluation settings (OpenRouter key + 3 model choices)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL_A,
    DEFAULT_MODEL_B,
    DEFAULT_MODEL_C,
)
from app.ai.openrouter import ping
from app.auth.deps import current_user
from app.db.models import User, UserAISettings
from app.db.session import get_db
from app.keys.crypto import decrypt, encrypt
from app.security import limiter


router = APIRouter(prefix="/settings/ai", tags=["settings", "ai"])


_AVAILABLE_IDS = {m["id"] for m in AVAILABLE_MODELS}


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
        row = UserAISettings(
            user_id=user_id,
            model_a=DEFAULT_MODEL_A,
            model_b=DEFAULT_MODEL_B,
            model_c=DEFAULT_MODEL_C,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def _validate_model(model_id: str) -> None:
    if model_id not in _AVAILABLE_IDS:
        raise HTTPException(400, f"unknown model id: {model_id}")


@router.get("")
async def get_ai_settings(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_or_create(db, user.id)
    return {
        "has_key": row.encrypted_openrouter_key is not None,
        "model_a": row.model_a,
        "model_b": row.model_b,
        "model_c": row.model_c,
        "available_models": AVAILABLE_MODELS,
    }


@router.put("")
async def put_ai_settings(
    body: AISettingsIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_or_create(db, user.id)
    if body.openrouter_api_key is not None:
        # Empty string = clear the stored key.
        if body.openrouter_api_key.strip() == "":
            row.encrypted_openrouter_key = None
        else:
            row.encrypted_openrouter_key = encrypt(body.openrouter_api_key.strip())
    if body.model_a:
        _validate_model(body.model_a)
        row.model_a = body.model_a
    if body.model_b:
        _validate_model(body.model_b)
        row.model_b = body.model_b
    if body.model_c:
        _validate_model(body.model_c)
        row.model_c = body.model_c
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
