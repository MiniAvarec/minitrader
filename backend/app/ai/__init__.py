"""AI evaluation feature (OpenRouter-backed deal reviews).

Three different models grade each deal in parallel; rows persist in
`order_evaluations`. Per-user API key is encrypted via the existing Fernet
MASTER_KEY pattern (see app/keys/crypto.py).

The Settings UI's model dropdown is populated at runtime from the live
OpenRouter catalog — see app.ai.catalog. The list below is a tiny last-resort
fallback used only when the catalog endpoint is unreachable and no prior
snapshot is cached.
"""
from __future__ import annotations


FALLBACK_MODELS: list[dict[str, str]] = [
    {"id": "anthropic/claude-opus-4.7", "label": "Claude Opus 4.7", "lab": "Anthropic"},
    {"id": "anthropic/claude-sonnet-4.6", "label": "Claude Sonnet 4.6", "lab": "Anthropic"},
    {"id": "openai/gpt-5", "label": "GPT-5", "lab": "OpenAI"},
    {"id": "google/gemini-2.5-pro", "label": "Gemini 2.5 Pro", "lab": "Google"},
    {"id": "x-ai/grok-4", "label": "Grok 4", "lab": "xAI"},
    {"id": "deepseek/deepseek-r1", "label": "DeepSeek R1", "lab": "DeepSeek"},
]


# Final hardcoded fallbacks for initial UserAISettings rows when the OpenRouter
# catalog has never been reached. The Settings UI shows the live catalog
# alongside any saved choice; users can re-pick after first load.
DEFAULT_MODEL_A = "anthropic/claude-opus-4.7"
DEFAULT_MODEL_B = "openai/gpt-5"
DEFAULT_MODEL_C = "google/gemini-2.5-pro"
