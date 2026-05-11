"""System + user prompts for AI deal evaluation.

The system prompt locks the output to a strict JSON schema. The user prompt
is a structured markdown brief built from the context dict from context.py.
"""
from __future__ import annotations

import json
from typing import Any


SYSTEM_PROMPT = (
    "You are an experienced discretionary crypto trading coach reviewing a "
    "single trade for an individual trader. Be specific, candid, and "
    "actionable. Anchor every claim to evidence in the supplied data "
    "(candles, indicators, risk limits, notes). Do not invent prices.\n\n"
    "Return ONLY a single JSON object with exactly these keys:\n"
    "  - verdict:    one of \"good\" | \"mixed\" | \"bad\"\n"
    "  - score:      integer 0–100 (overall setup quality)\n"
    "  - summary:    2–3 sentence plain-English verdict\n"
    "  - strengths:  array of 3–5 short bullets (what was right)\n"
    "  - weaknesses: array of 3–5 short bullets (what was wrong)\n"
    "  - suggestions: array of 3–5 short bullets (concrete next-time actions)\n\n"
    "No prose outside the JSON. No code fences. No keys other than the six above."
)


def _candles_table(rows: list[dict], limit: int = 30) -> str:
    """Compact tabular rendering of candles to save tokens vs. raw JSON."""
    if not rows:
        return "(no data)"
    head = rows[-limit:]
    lines = ["t,o,h,l,c,v"]
    for c in head:
        lines.append(
            f"{c['t']},{c['o']},{c['h']},{c['l']},{c['c']},{c['v']}"
        )
    return "```\n" + "\n".join(lines) + "\n```"


def build_user_prompt(ctx: dict[str, Any]) -> str:
    is_open = bool(ctx.get("is_open"))
    deal = ctx["deal"]
    strat = ctx.get("strategy") or {}
    risk = ctx.get("risk_limits")
    der = ctx.get("derived") or {}
    candles = ctx.get("candles") or {}
    md_err = ctx.get("market_data_error")

    instruction = (
        "This deal is **still open**. Review the *setup quality* and current "
        "management: was the entry timing reasonable, is the stop placed well "
        "relative to volatility (ATR), is the risk:reward sensible, and does "
        "the live action since entry confirm or invalidate the thesis?"
        if is_open
        else
        "This deal is **closed**. Perform a full post-trade review: judge the "
        "setup quality, the exit, the risk management, and attribute the "
        "outcome — was a win lucky or earned? Was a loss a thesis failure or "
        "an execution failure?"
    )

    out: list[str] = []
    out.append(f"## Task\n\n{instruction}\n")

    out.append("## Deal Facts\n")
    out.append(
        "```json\n"
        + json.dumps(deal, indent=2, default=str)
        + "\n```"
    )

    out.append("\n## Strategy")
    if strat.get("name"):
        out.append(f"**Name:** {strat['name']}")
    if strat.get("params"):
        out.append(
            "**Config:**\n```json\n"
            + json.dumps(strat["params"], indent=2, default=str)
            + "\n```"
        )
    if not strat.get("name") and not strat.get("params"):
        out.append("_(manual / discretionary trade — no linked strategy)_")

    out.append("\n## Derived Metrics (computed at entry)")
    out.append("```json\n" + json.dumps(der, indent=2, default=str) + "\n```")

    if risk:
        out.append("\n## User Risk Limits")
        out.append("```json\n" + json.dumps(risk, indent=2, default=str) + "\n```")

    if md_err:
        out.append(
            f"\n## Market Context\n_Market data unavailable: {md_err}_\n"
            "Review based on deal facts only and note this caveat."
        )
    else:
        out.append("\n## Higher-TF Context (4h, ending at entry)")
        out.append(_candles_table(candles.get("tf_4h_pre_entry") or [], limit=30))

        out.append("\n## 1h Candles Before Entry")
        out.append(_candles_table(candles.get("tf_1h_pre_entry") or [], limit=50))

        out.append("\n## 5m Candles Around Entry (last 24)")
        out.append(_candles_table(candles.get("tf_5m_pre_entry") or [], limit=24))

        post_label = (
            "1h Candles Since Entry (live)" if is_open else "1h Candles Entry → Close"
        )
        out.append(f"\n## {post_label}")
        out.append(_candles_table(candles.get("tf_1h_post_entry") or [], limit=50))

    if deal.get("notes"):
        out.append("\n## User Notes")
        out.append(f"> {deal['notes']}")
    if deal.get("tags"):
        out.append("\n## User Tags")
        out.append(", ".join(f"`{t}`" for t in deal["tags"]))

    out.append(
        "\n---\nReturn the JSON object now. Remember: strict JSON only, "
        "no prose outside it."
    )
    return "\n".join(out)
