"""Binance USDT-M Futures kline ingestor.

Subscribes to the public combined-streams WebSocket for each (symbol, timeframe)
and pushes klines to Redis as a rolling window. Closed klines also publish
a `kline_closed` event on the signals channel — the signal worker uses this
as a tick to re-evaluate.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx
import websockets

from app.config import get_settings
from app.data.redis_io import (
    SIGNAL_CHANNEL,
    get_klines,
    klines_key,
    make_redis,
    push_kline,
    replace_last_kline,
)

log = logging.getLogger("ingestor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def _ws_base() -> str:
    if get_settings().BINANCE_USE_TESTNET:
        return "wss://stream.binancefuture.com/stream"
    return "wss://fstream.binance.com/stream"


def _rest_base() -> str:
    if get_settings().BINANCE_USE_TESTNET:
        return "https://testnet.binancefuture.com"
    return "https://fapi.binance.com"


def _build_streams(symbols: list[str], tfs: list[str]) -> str:
    parts = [f"{s.lower()}@kline_{tf}" for s in symbols for tf in tfs]
    return "/".join(parts)


def _normalize(k: dict) -> dict:
    return {
        "open_time": int(k["t"]),
        "close_time": int(k["T"]),
        "open": float(k["o"]),
        "high": float(k["h"]),
        "low": float(k["l"]),
        "close": float(k["c"]),
        "volume": float(k["v"]),
        "closed": bool(k["x"]),
    }


async def _seed_history(r, symbols: list[str], tfs: list[str]) -> None:
    """Backfill rolling window from REST so indicators have history at boot."""
    base = _rest_base()
    async with httpx.AsyncClient(base_url=base, timeout=15.0) as client:
        for s in symbols:
            for tf in tfs:
                # Skip if already populated
                existing = await get_klines(r, s, tf, limit=1)
                if len(existing) >= 200:
                    continue
                try:
                    resp = await client.get(
                        "/fapi/v1/klines",
                        params={"symbol": s, "interval": tf, "limit": 500},
                    )
                    resp.raise_for_status()
                    rows = resp.json()
                except Exception as e:
                    log.warning("seed %s %s failed: %s", s, tf, e)
                    continue
                # Reset key
                await r.delete(klines_key(s, tf))
                for row in rows:
                    k = {
                        "open_time": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                        "close_time": int(row[6]),
                        "closed": True,
                    }
                    await push_kline(r, s, tf, k)
                log.info("seeded %s %s with %d klines", s, tf, len(rows))


async def run() -> None:
    s = get_settings()
    symbols = s.symbols
    tfs = s.timeframes
    streams = _build_streams(symbols, tfs)
    url = f"{_ws_base()}?streams={streams}"
    r = make_redis()
    await _seed_history(r, symbols, tfs)

    while True:
        try:
            log.info("connecting WS %s", url)
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                async for raw in ws:
                    msg: dict[str, Any] = json.loads(raw)
                    data = msg.get("data") or msg
                    k = data.get("k")
                    if not k:
                        continue
                    symbol = data.get("s") or k.get("s")
                    tf = k.get("i")
                    norm = _normalize(k)
                    if norm["closed"]:
                        await push_kline(r, symbol, tf, norm)
                        await r.publish(
                            SIGNAL_CHANNEL,
                            json.dumps({"event": "kline_closed", "symbol": symbol, "tf": tf}),
                        )
                    else:
                        await replace_last_kline(r, symbol, tf, norm)
        except Exception as e:
            log.warning("WS error: %s; reconnecting in 3s", e)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(run())
