"""Multi-exchange broker factory.

Single entry point for instantiating a `Broker` from `(exchange, credentials)`.
Replaces the hardcoded `BinanceBroker(...)` call sites scattered through the app.
"""
from __future__ import annotations

from typing import Type

from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import Broker
from app.brokers.binance import BinanceBroker
from app.brokers.bybit import BybitBroker
from app.brokers.okx import OKXBroker
from app.keys.store import load_key


SUPPORTED: dict[str, Type[Broker]] = {
    "binance": BinanceBroker,
    "okx": OKXBroker,
    "bybit": BybitBroker,
}


def get_broker(
    exchange: str,
    api_key: str,
    api_secret: str,
    *,
    testnet: bool = True,
    passphrase: str | None = None,
) -> Broker:
    cls = SUPPORTED.get(exchange)
    if cls is None:
        raise ValueError(f"unsupported exchange: {exchange}")
    if exchange == "okx":
        return cls(api_key, api_secret, testnet=testnet, passphrase=passphrase)  # type: ignore[call-arg]
    return cls(api_key, api_secret, testnet=testnet)


async def get_broker_for_user(
    db: AsyncSession, user_id: int, exchange: str, *, label: str = "default"
) -> Broker | None:
    loaded = await load_key(db, user_id, exchange, label)
    if not loaded:
        return None
    api_key, api_secret, testnet, passphrase = loaded
    return get_broker(
        exchange, api_key, api_secret, testnet=testnet, passphrase=passphrase
    )
