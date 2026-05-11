"""Live OpenRouter model catalog.

OpenRouter publishes its catalog at /api/v1/models (no auth required). We
fetch it on demand, filter down to "frontier" tier, cache the result for an
hour, and fall back to a small hardcoded list when the network is down.

"Frontier" is defined as: top model from a known major lab, with non-frontier
suffixes (mini, flash, haiku, nano, small, distill, etc.) stripped out.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.ai import FALLBACK_MODELS


_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_CACHE_TTL_SECONDS = 60 * 60


# Author prefixes whose top-tier models we surface. Order here also drives the
# default-picker preference (Anthropic first, then OpenAI, then Google, …).
_FRONTIER_LABS: dict[str, str] = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google",
    "x-ai": "xAI",
    "deepseek": "DeepSeek",
    "meta-llama": "Meta",
    "qwen": "Qwen",
    "mistralai": "Mistral",
}


# Substrings in the model portion (after the slash) that disqualify a model
# from "frontier" — small / distilled / preview / non-text variants.
_EXCLUDE_TOKENS: tuple[str, ...] = (
    "haiku",
    "mini",
    "nano",
    "flash",
    "lite",
    "small",
    "tiny",
    "embed",
    "vision-only",
    "guard",
    "distill",
    "1.5b",
    "3b",
    "7b",
    "8b",
    "13b",
    "instruct-7b",
    "instruct-8b",
)


_cache_lock = asyncio.Lock()
_cache: dict[str, Any] = {"at": 0.0, "models": []}


def _lab_for(model_id: str) -> str | None:
    prefix = model_id.split("/", 1)[0].lower()
    return _FRONTIER_LABS.get(prefix)


def _is_frontier(model_id: str, modality: str | None) -> bool:
    if "/" not in model_id:
        return False
    if _lab_for(model_id) is None:
        return False
    # Skip free / experimental / beta variant tags.
    if any(tag in model_id for tag in (":free", ":beta", ":nitro", ":extended", ":online")):
        return False
    suffix = model_id.split("/", 1)[1].lower()
    for tok in _EXCLUDE_TOKENS:
        if tok in suffix:
            return False
    # Only text-capable models (skip image-gen / embeddings).
    if modality and "text" not in modality.lower():
        return False
    return True


def _label_from(name: str, model_id: str) -> str:
    if name:
        return name
    return model_id.split("/", 1)[-1]


async def _fetch_openrouter_catalog() -> list[dict] | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(_OPENROUTER_MODELS_URL)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None

    out: list[dict] = []
    for m in rows:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if not isinstance(mid, str):
            continue
        # `architecture.modality` may be e.g. "text->text", "text+image->text".
        arch = m.get("architecture") or {}
        modality = arch.get("modality") if isinstance(arch, dict) else None
        if not _is_frontier(mid, modality):
            continue
        lab = _lab_for(mid) or "Other"
        out.append(
            {
                "id": mid,
                "label": _label_from(m.get("name") or "", mid),
                "lab": lab,
                "created": int(m.get("created") or 0),
                "context_length": m.get("context_length"),
            }
        )

    # Sort: by lab (in our preferred order), then newest first within each lab.
    lab_order = list(_FRONTIER_LABS.values())
    out.sort(
        key=lambda x: (
            lab_order.index(x["lab"]) if x["lab"] in lab_order else len(lab_order),
            -x["created"],
            x["id"],
        )
    )
    return out


async def get_available_models(force: bool = False) -> list[dict]:
    """Return frontier-tier OpenRouter models, cached for 1h.

    Falls back to FALLBACK_MODELS when the catalog is unreachable AND we have
    no prior cached snapshot. A stale snapshot is preferred over the fallback.
    """
    now = time.monotonic()
    if not force and _cache["models"] and (now - _cache["at"]) < _CACHE_TTL_SECONDS:
        return _cache["models"]

    async with _cache_lock:
        # Double-check under the lock to avoid a thundering herd.
        if (
            not force
            and _cache["models"]
            and (time.monotonic() - _cache["at"]) < _CACHE_TTL_SECONDS
        ):
            return _cache["models"]
        fresh = await _fetch_openrouter_catalog()
        if fresh:
            _cache["models"] = fresh
            _cache["at"] = time.monotonic()
            return fresh
        if _cache["models"]:
            # Network blip — keep serving the stale snapshot until the next try.
            return _cache["models"]
        return list(FALLBACK_MODELS)


async def pick_default_models() -> tuple[str, str, str]:
    """Pick top-3 frontier models from major labs as initial defaults.

    Tries Anthropic → OpenAI → Google → xAI → DeepSeek in that order, picking
    the newest model from each lab. Falls through to whatever's available if
    fewer than 3 labs are represented.
    """
    models = await get_available_models()
    if not models:
        return (
            "anthropic/claude-opus-4.7",
            "openai/gpt-5",
            "google/gemini-2.5-pro",
        )
    by_lab: dict[str, str] = {}
    for m in models:
        by_lab.setdefault(m["lab"], m["id"])
    picked: list[str] = []
    for pref in ("Anthropic", "OpenAI", "Google", "xAI", "DeepSeek", "Meta"):
        mid = by_lab.get(pref)
        if mid and mid not in picked:
            picked.append(mid)
        if len(picked) == 3:
            break
    if len(picked) < 3:
        for m in models:
            if m["id"] not in picked:
                picked.append(m["id"])
            if len(picked) == 3:
                break
    while len(picked) < 3:
        picked.append(picked[-1])
    return (picked[0], picked[1], picked[2])


def ensure_in_list(available: list[dict], model_id: str) -> list[dict]:
    """Make sure the user's saved model_id is present in the dropdown options.

    The live catalog can rotate; if the user picked a model that has since
    been removed (or renamed), we still want their Select to display the
    saved value rather than render blank.
    """
    if not model_id:
        return available
    if any(m["id"] == model_id for m in available):
        return available
    prefix = model_id.split("/", 1)[0]
    lab = _FRONTIER_LABS.get(prefix.lower()) or prefix.title()
    return list(available) + [
        {
            "id": model_id,
            "label": _label_from("", model_id) + " (legacy)",
            "lab": lab,
        }
    ]
