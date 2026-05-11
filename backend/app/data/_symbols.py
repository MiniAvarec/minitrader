"""Symbol extraction shared across news sources.

Maps free-form text (headlines, related-asset fields, entity mentions) to the
exchange-style USDT-perp tickers our watchlist uses (e.g. "BTCUSDT").
"""
from __future__ import annotations

import re

# Bases we care about — kept aligned with the most commonly-watched perps.
# If you add a new base here, also add the spelt-out form below in NAME_TO_BASE.
TRACKED_BASES: tuple[str, ...] = (
    "BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "DOT", "LINK",
    "MATIC", "TRX", "TON", "LTC", "BCH", "ARB", "OP", "SUI", "APT", "ATOM",
    "NEAR", "FIL", "ETC", "XLM", "HBAR", "ICP", "INJ", "RNDR", "TIA", "SEI",
)

NAME_TO_BASE: dict[str, str] = {
    "BITCOIN": "BTC",
    "ETHEREUM": "ETH",
    "SOLANA": "SOL",
    "RIPPLE": "XRP",
    "DOGECOIN": "DOGE",
    "CARDANO": "ADA",
    "AVALANCHE": "AVAX",
    "POLKADOT": "DOT",
    "CHAINLINK": "LINK",
    "POLYGON": "MATIC",
    "TRON": "TRX",
    "TONCOIN": "TON",
    "LITECOIN": "LTC",
    "ARBITRUM": "ARB",
    "OPTIMISM": "OP",
    "APTOS": "APT",
    "COSMOS": "ATOM",
    "FILECOIN": "FIL",
    "STELLAR": "XLM",
    "HEDERA": "HBAR",
    "INTERNET COMPUTER": "ICP",
    "INJECTIVE": "INJ",
    "RENDER": "RNDR",
    "CELESTIA": "TIA",
}

_QUOTE = "USDT"
_TRACKED = set(TRACKED_BASES)
_TOKEN_RE = re.compile(r"[A-Za-z]+")


def to_perp(base: str) -> str:
    return f"{base.upper()}{_QUOTE}"


def extract_symbols(*texts: str) -> list[str]:
    """Find tracked-base mentions across any number of strings.

    Each text is split on non-letter tokens and checked against TRACKED_BASES;
    each full string is also scanned for spelled-out names (case-insensitive).
    Returns sorted unique USDT-perp tickers.
    """
    found: set[str] = set()
    for text in texts:
        if not text:
            continue
        upper = text.upper()
        for tok in _TOKEN_RE.findall(upper):
            if tok in _TRACKED:
                found.add(to_perp(tok))
        for name, base in NAME_TO_BASE.items():
            if name in upper:
                found.add(to_perp(base))
    return sorted(found)


def code_to_perp(code: str) -> str | None:
    """Map an exchange-style base code (e.g. 'BTC') to a perp ticker, if tracked."""
    base = (code or "").upper().strip()
    if base in _TRACKED:
        return to_perp(base)
    return None
