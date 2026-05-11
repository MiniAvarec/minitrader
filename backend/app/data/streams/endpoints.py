"""Per-exchange WS endpoint table (primary + standby).

The streams manager configures the standby ccxt.pro client with the alternate
URL so the two redundant connections actually traverse different infrastructure.
"""
from __future__ import annotations


# (primary_ws, standby_ws) per (exchange, testnet)
ENDPOINTS: dict[tuple[str, bool], tuple[str, str]] = {
    ("binance", False): (
        "wss://fstream.binance.com",
        "wss://fstream-auth.binance.com",
    ),
    ("binance", True): (
        "wss://stream.binancefuture.com",
        "wss://stream.binancefuture.com",
    ),
    ("okx", False): (
        "wss://ws.okx.com:8443",
        "wss://wsaws.okx.com:8443",
    ),
    ("okx", True): (
        "wss://wspap.okx.com:8443",
        "wss://wspap.okx.com:8443",
    ),
    ("bybit", False): (
        "wss://stream.bybit.com",
        "wss://stream.bytick.com",
    ),
    ("bybit", True): (
        "wss://stream-testnet.bybit.com",
        "wss://stream-testnet.bybit.com",
    ),
}


def get_endpoints(exchange: str, testnet: bool) -> tuple[str, str]:
    return ENDPOINTS.get((exchange, testnet), ("", ""))
