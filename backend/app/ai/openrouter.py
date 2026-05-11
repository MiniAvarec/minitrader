"""Thin async OpenRouter chat-completions client.

OpenRouter is OpenAI-API-compatible. We use it to fan out to three different
foundation models with a single key. Forces JSON-object output for our prompts.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import get_settings


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(Exception):
    pass


async def chat_completion(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    json_mode: bool = True,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Call OpenRouter once. Returns a dict with parsed content + token/cost metadata.

    Raises OpenRouterError on HTTP / parse failure so the caller can persist
    a clean per-model error row instead of crashing the whole 3-model fan-out.
    """
    s = get_settings()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # OpenRouter recommends these for traceability + free-tier eligibility.
        "HTTP-Referer": s.FRONTEND_ORIGIN,
        "X-Title": "minitrader",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        # Generous cap — trade reviews are bounded; this just prevents runaways.
        "max_tokens": 1500,
        "temperature": 0.2,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(OPENROUTER_URL, headers=headers, json=body)
    except httpx.HTTPError as e:
        raise OpenRouterError(f"network error: {e}") from e

    if r.status_code != 200:
        # OpenRouter returns structured errors — surface the message.
        detail: str
        try:
            data = r.json()
            detail = (
                data.get("error", {}).get("message")
                if isinstance(data, dict)
                else str(data)
            ) or r.text
        except Exception:
            detail = r.text
        raise OpenRouterError(f"HTTP {r.status_code}: {detail[:400]}")

    data = r.json()
    try:
        choice = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise OpenRouterError(f"malformed response: {e}") from e

    parsed: dict[str, Any] | None = None
    if json_mode:
        try:
            parsed = json.loads(choice)
        except json.JSONDecodeError:
            # Some models return JSON wrapped in ```json fences despite response_format.
            stripped = choice.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise OpenRouterError(f"non-JSON content: {e}") from e

    usage = data.get("usage") or {}
    return {
        "content_text": choice,
        "content_json": parsed,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        # OpenRouter populates `usage.cost` (USD) on most providers.
        "cost_usd": (usage.get("cost") if isinstance(usage.get("cost"), (int, float)) else None),
        "raw": data,
    }


async def ping(api_key: str, model: str) -> tuple[bool, str]:
    """Cheap connectivity test used by Settings → Test connection."""
    try:
        out = await chat_completion(
            api_key=api_key,
            model=model,
            system="You are a JSON echo. Reply with {\"ok\": true}.",
            user="ping",
            json_mode=True,
            timeout=20.0,
        )
        ok = bool((out.get("content_json") or {}).get("ok"))
        return (ok, "ok" if ok else "unexpected response")
    except OpenRouterError as e:
        return (False, str(e))
