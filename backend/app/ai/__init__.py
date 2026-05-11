"""AI evaluation feature (OpenRouter-backed deal reviews).

Three different models grade each deal in parallel; rows persist in
`order_evaluations`. Per-user API key is encrypted via the existing Fernet
MASTER_KEY pattern (see app/keys/crypto.py).
"""
from __future__ import annotations

# Curated picklist surfaced to the frontend Settings → AI Evaluation card.
# Mixed labs on purpose — diverse perspectives are the point of running 3.
AVAILABLE_MODELS: list[dict[str, str]] = [
    {"id": "anthropic/claude-opus-4.7", "label": "Claude Opus 4.7", "lab": "Anthropic"},
    {"id": "anthropic/claude-sonnet-4.6", "label": "Claude Sonnet 4.6", "lab": "Anthropic"},
    {"id": "anthropic/claude-haiku-4.5", "label": "Claude Haiku 4.5", "lab": "Anthropic"},
    {"id": "openai/gpt-5", "label": "GPT-5", "lab": "OpenAI"},
    {"id": "openai/gpt-5-mini", "label": "GPT-5 mini", "lab": "OpenAI"},
    {"id": "openai/o4", "label": "o4", "lab": "OpenAI"},
    {"id": "google/gemini-2.5-pro", "label": "Gemini 2.5 Pro", "lab": "Google"},
    {"id": "google/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "lab": "Google"},
    {"id": "deepseek/deepseek-r1", "label": "DeepSeek R1", "lab": "DeepSeek"},
    {"id": "x-ai/grok-4", "label": "Grok 4", "lab": "xAI"},
]

DEFAULT_MODEL_A = "anthropic/claude-opus-4.7"
DEFAULT_MODEL_B = "openai/gpt-5"
DEFAULT_MODEL_C = "google/gemini-2.5-pro"
