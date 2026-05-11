"""Redis helpers for kline cache and pubsub.

Multi-exchange: kline keys include the exchange (`klines:{EXCHANGE}:{SYMBOL}:{TF}`).
Legacy single-arg helpers are removed; callers must pass an exchange.
"""
from __future__ import annotations

import json
from typing import Iterable

import redis.asyncio as redis

from app.config import get_settings

KLINE_LIMIT = 500  # rolling window per (exchange, symbol, tf)
SIGNAL_CHANNEL = "signals"
NEWS_CHANNEL = "news"
WATCHLIST_CHANGED_CHANNEL = "watchlist:changed"
KEYS_CHANGED_CHANNEL = "keys:changed"
INSTRUMENTS_REFRESH_CHANNEL_PREFIX = "instruments:refresh:"


def make_redis() -> "redis.Redis":
    return redis.from_url(get_settings().REDIS_URL, decode_responses=True)


def klines_key(exchange: str, symbol: str, tf: str) -> str:
    return f"klines:{exchange.lower()}:{symbol.upper()}:{tf}"


async def push_kline(
    r: "redis.Redis", exchange: str, symbol: str, tf: str, kline: dict
) -> None:
    key = klines_key(exchange, symbol, tf)
    await r.rpush(key, json.dumps(kline))
    await r.ltrim(key, -KLINE_LIMIT, -1)


async def replace_last_kline(
    r: "redis.Redis", exchange: str, symbol: str, tf: str, kline: dict
) -> None:
    key = klines_key(exchange, symbol, tf)
    pipe = r.pipeline()
    pipe.rpop(key)
    pipe.rpush(key, json.dumps(kline))
    pipe.ltrim(key, -KLINE_LIMIT, -1)
    await pipe.execute()


async def get_klines(
    r: "redis.Redis", exchange: str, symbol: str, tf: str, limit: int = KLINE_LIMIT
) -> list[dict]:
    key = klines_key(exchange, symbol, tf)
    raw = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in raw]


async def publish_signal(r: "redis.Redis", payload: dict) -> None:
    await r.publish(SIGNAL_CHANNEL, json.dumps(payload))


async def publish_news(r: "redis.Redis", payload: dict) -> None:
    await r.publish(NEWS_CHANNEL, json.dumps(payload))


async def subscribe(r: "redis.Redis", channels: Iterable[str]):
    pubsub = r.pubsub()
    await pubsub.subscribe(*channels)
    return pubsub
