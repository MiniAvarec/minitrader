"""POST /journal/deals/{id}/evaluate and GET /journal/deals/{id}/evaluations.

Fans out 3 OpenRouter calls in parallel for one deal and persists each result
as a row in `order_evaluations`. The 3 cards rendered in the UI come from this
table, latest-per-model.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_eval_context
from app.ai.openrouter import OpenRouterError, chat_completion
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.auth.deps import current_user
from app.db.models import Order, OrderEvaluation, User, UserAISettings
from app.db.session import get_db
from app.keys.crypto import decrypt
from app.security import limiter


router = APIRouter(prefix="/journal/deals", tags=["journal", "ai"])


_VALID_VERDICTS = {"good", "mixed", "bad"}


def _clean_list(v: Any, *, max_items: int = 8, max_len: int = 280) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for item in v:
        if not isinstance(item, str):
            item = str(item)
        item = item.strip()
        if item:
            out.append(item[:max_len])
        if len(out) >= max_items:
            break
    return out


def _normalize_result(parsed: dict[str, Any] | None) -> dict[str, Any]:
    """Coerce the model's JSON into our schema; tolerate small variations."""
    if not isinstance(parsed, dict):
        return {
            "verdict": None,
            "score": None,
            "summary": None,
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
        }
    verdict_raw = (parsed.get("verdict") or "").strip().lower()
    verdict = verdict_raw if verdict_raw in _VALID_VERDICTS else None
    score = parsed.get("score")
    try:
        score_int = int(score) if score is not None else None
        if score_int is not None:
            score_int = max(0, min(100, score_int))
    except (TypeError, ValueError):
        score_int = None
    summary = parsed.get("summary")
    if summary is not None and not isinstance(summary, str):
        summary = str(summary)
    return {
        "verdict": verdict,
        "score": score_int,
        "summary": (summary or "").strip()[:2000] or None,
        "strengths": _clean_list(parsed.get("strengths")),
        "weaknesses": _clean_list(parsed.get("weaknesses")),
        "suggestions": _clean_list(parsed.get("suggestions")),
    }


def _row_to_dict(row: OrderEvaluation) -> dict[str, Any]:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "model": row.model,
        "status": row.status,
        "verdict": row.verdict,
        "score": row.score,
        "summary": row.summary,
        "strengths": list(row.strengths or []),
        "weaknesses": list(row.weaknesses or []),
        "suggestions": list(row.suggestions or []),
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "cost_usd": row.cost_usd,
        "error": row.error,
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


async def _run_one(
    api_key: str, model: str, system: str, user_prompt: str
) -> dict[str, Any]:
    """Wraps chat_completion to always return a structured result (never raises)."""
    try:
        out = await chat_completion(
            api_key=api_key,
            model=model,
            system=system,
            user=user_prompt,
            json_mode=True,
            timeout=90.0,
        )
        normalized = _normalize_result(out.get("content_json"))
        return {
            "ok": True,
            "model": model,
            "normalized": normalized,
            "prompt_tokens": out.get("prompt_tokens"),
            "completion_tokens": out.get("completion_tokens"),
            "cost_usd": out.get("cost_usd"),
            "raw": out.get("raw"),
        }
    except OpenRouterError as e:
        return {"ok": False, "model": model, "error": str(e)[:500]}
    except Exception as e:
        return {"ok": False, "model": model, "error": f"{type(e).__name__}: {e}"[:500]}


@router.post("/{deal_id}/evaluate")
@limiter.limit("20/hour")
async def evaluate_deal(
    request: Request,
    deal_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    order = (
        await db.execute(
            select(Order).where(and_(Order.id == deal_id, Order.user_id == user.id))
        )
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(404, "deal not found")

    ai_cfg = (
        await db.execute(
            select(UserAISettings).where(UserAISettings.user_id == user.id)
        )
    ).scalar_one_or_none()
    if ai_cfg is None or ai_cfg.encrypted_openrouter_key is None:
        raise HTTPException(
            400,
            "OpenRouter key not configured — open Settings → AI Evaluation to add one.",
        )
    try:
        api_key = decrypt(ai_cfg.encrypted_openrouter_key)
    except Exception:
        raise HTTPException(500, "failed to decrypt stored key — re-enter it in Settings")

    models = [ai_cfg.model_a, ai_cfg.model_b, ai_cfg.model_c]

    # Build context once and reuse it for all three models.
    ctx = await build_eval_context(db, user, order)
    user_prompt = build_user_prompt(ctx)

    results = await asyncio.gather(
        *(_run_one(api_key, m, SYSTEM_PROMPT, user_prompt) for m in models)
    )

    now = datetime.now(timezone.utc)
    saved: list[OrderEvaluation] = []
    for res in results:
        row = OrderEvaluation(
            user_id=user.id,
            order_id=order.id,
            model=res["model"],
            created_at=now,
            completed_at=now,
        )
        if res.get("ok"):
            norm = res["normalized"]
            row.status = "done"
            row.verdict = norm["verdict"]
            row.score = norm["score"]
            row.summary = norm["summary"]
            row.strengths = norm["strengths"]
            row.weaknesses = norm["weaknesses"]
            row.suggestions = norm["suggestions"]
            row.prompt_tokens = res.get("prompt_tokens")
            row.completion_tokens = res.get("completion_tokens")
            row.cost_usd = res.get("cost_usd")
            row.raw_response = None  # raw is large; skip persisting unless debugging
        else:
            row.status = "error"
            row.error = res.get("error") or "unknown error"
        db.add(row)
        saved.append(row)

    await db.commit()
    for row in saved:
        await db.refresh(row)

    return {
        "deal_id": order.id,
        "evaluations": [_row_to_dict(r) for r in saved],
    }


@router.get("/{deal_id}/evaluations")
async def list_deal_evaluations(
    deal_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    # Confirm ownership.
    order = (
        await db.execute(
            select(Order.id).where(and_(Order.id == deal_id, Order.user_id == user.id))
        )
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(404, "deal not found")

    # Most-recent N rows for this order — frontend dedupes by model.
    rows = (
        (
            await db.execute(
                select(OrderEvaluation)
                .where(OrderEvaluation.order_id == deal_id)
                .order_by(desc(OrderEvaluation.created_at))
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    # Keep only the most recent row per model.
    seen: set[str] = set()
    latest: list[OrderEvaluation] = []
    for r in rows:
        if r.model in seen:
            continue
        seen.add(r.model)
        latest.append(r)
    return {"deal_id": deal_id, "evaluations": [_row_to_dict(r) for r in latest]}
