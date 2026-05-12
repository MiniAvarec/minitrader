"""Multi-exchange broker factory.

Single entry point for instantiating a `Broker` from `(exchange, credentials)`.
Replaces the hardcoded `BinanceBroker(...)` call sites scattered through the app.

The decrypted-credentials tuple is cached briefly per `(user_id, exchange)` so
that bursty endpoints (e.g. /positions and /portfolio loop over every keyed
exchange) don't re-decrypt on every call. Broker instances themselves are
*not* cached — each request gets a fresh CCXT client to avoid sharing the
underlying aiohttp session across coroutines.
"""
from __future__ import annotations

import json
import os
from typing import Type

from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import Broker
from app.brokers.binance import BinanceBroker
from app.brokers.bybit import BybitBroker
from app.brokers.ibkr import IBKRBroker
from app.brokers.okx import OKXBroker
from app.keys.store import load_key


SUPPORTED: dict[str, Type[Broker]] = {
    "binance": BinanceBroker,
    "okx": OKXBroker,
    "bybit": BybitBroker,
    "ibkr": IBKRBroker,
}


# Cache holds (api_key, api_secret, testnet, passphrase, connection_config) keyed by
# (user_id, exchange, label). 60s TTL trades a small staleness window for
# avoiding a DB hit + Fernet decrypt on every /positions refresh.
_CRED_CACHE: TTLCache[
    tuple[int, str, str], tuple[str, str, bool, str | None, str | None]
] = TTLCache(maxsize=128, ttl=60)


def invalidate_user_creds(user_id: int, exchange: str | None = None) -> None:
    """Drop cached credentials for a user, e.g. after they upload a new key."""
    if exchange is None:
        for k in [k for k in _CRED_CACHE if k[0] == user_id]:
            _CRED_CACHE.pop(k, None)
        return
    for k in [k for k in _CRED_CACHE if k[0] == user_id and k[1] == exchange]:
        _CRED_CACHE.pop(k, None)


def _ibkr_default_client_id() -> int:
    """ClientId for REST-driven (UI / settings test) IBKR connections.

    IBKR rejects duplicate clientIds on the same gateway, so worker services
    pick different values from env (see Phase 6). This is the fallback for
    short-lived REST calls; defaults to 4.
    """
    try:
        return int(os.environ.get("IBKR_CLIENT_ID_REST", "4"))
    except ValueError:
        return 4


def get_broker(
    exchange: str,
    api_key: str,
    api_secret: str,
    *,
    testnet: bool = True,
    passphrase: str | None = None,
    connection_config: str | None = None,
) -> Broker:
    cls = SUPPORTED.get(exchange)
    if cls is None:
        raise ValueError(f"unsupported exchange: {exchange}")
    if exchange == "okx":
        return cls(api_key, api_secret, testnet=testnet, passphrase=passphrase)  # type: ignore[call-arg]
    if exchange == "ibkr":
        cfg = json.loads(connection_config or "{}")
        host = cfg.get("host") or "ibgateway"
        port = int(cfg.get("port") or (4002 if testnet else 4001))
        client_id = int(cfg.get("client_id") or _ibkr_default_client_id())
        account = cfg.get("account") or None
        return IBKRBroker(
            host=host,
            port=port,
            client_id=client_id,
            account=account,
            testnet=testnet,
        )
    return cls(api_key, api_secret, testnet=testnet)


async def get_broker_for_user(
    db: AsyncSession, user_id: int, exchange: str, *, label: str = "default"
) -> Broker | None:
    cache_key = (user_id, exchange, label)
    cached = _CRED_CACHE.get(cache_key)
    if cached is None:
        loaded = await load_key(db, user_id, exchange, label)
        if not loaded:
            return None
        cached = loaded
        _CRED_CACHE[cache_key] = cached
    api_key, api_secret, testnet, passphrase, connection_config = cached
    return get_broker(
        exchange,
        api_key,
        api_secret,
        testnet=testnet,
        passphrase=passphrase,
        connection_config=connection_config,
    )
