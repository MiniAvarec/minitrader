"""Async OKX USDT-margined swap broker (ccxt + ccxt.pro).

OKX requires an API passphrase in addition to key+secret. Private user-data
fills come via `ccxt.pro.watch_orders` which handles login + subscription.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator

import ccxt.async_support as ccxt_async

try:
    import ccxt.pro as ccxt_pro
except Exception:  # pragma: no cover
    ccxt_pro = None  # type: ignore[assignment]

from app.brokers.base import (
    Broker,
    FillEvent,
    InstrumentInfo,
    KlineMsg,
    to_ccxt_symbol,
)


log = logging.getLogger("brokers.okx")


class OKXBroker(Broker):
    exchange_id = "okx"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        testnet: bool = True,
        passphrase: str | None = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase or ""
        self.testnet = testnet
        self.client = ccxt_async.okx(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "password": self.passphrase,
                "enableRateLimit": True,
                "options": {"defaultType": "swap"},
            }
        )
        if testnet:
            self.client.set_sandbox_mode(True)
        self._pro_client = None

    async def usdt_balance(self) -> float:
        bal = await self.client.fetch_balance(params={"type": "swap"})
        return float(bal.get("USDT", {}).get("free", 0.0))

    async def positions(self) -> list[dict]:
        raw = await self.client.fetch_positions()
        out: list[dict] = []
        for p in raw:
            contracts = float(p.get("contracts") or 0.0)
            if contracts == 0:
                continue
            out.append(
                {
                    "symbol": p.get("symbol"),
                    "side": p.get("side"),
                    "contracts": contracts,
                    "notional": float(p.get("notional") or 0.0),
                    "entry_price": float(p.get("entryPrice") or 0.0),
                    "mark_price": float(p.get("markPrice") or 0.0),
                    "unrealized_pnl": float(p.get("unrealizedPnl") or 0.0),
                    "leverage": float(p.get("leverage") or 0.0),
                }
            )
        return out

    async def mark_price(self, symbol: str) -> float:
        t = await self.client.fetch_ticker(symbol)
        return float(t.get("last") or t.get("close") or 0.0)

    async def place_market(
        self,
        symbol: str,
        side: str,
        qty: float,
        *,
        sl: float | None = None,
        tp: float | None = None,
        reduce_only: bool = False,
    ) -> dict:
        # OKX supports attaching SL/TP via algo params on the main order.
        params: dict = {"tdMode": "cross"}
        if reduce_only:
            params["reduceOnly"] = True
        if sl:
            params["stopLossPrice"] = sl
            params["slOrdPx"] = "-1"  # market trigger
        if tp:
            params["takeProfitPrice"] = tp
            params["tpOrdPx"] = "-1"
        return await self.client.create_order(symbol, "market", side, qty, None, params)

    async def fetch_realized_pnl(self, symbol: str, since_ms: int) -> float:
        # OKX bills endpoint includes "realized_pnl" rows.
        rows = await self.client.fetch_ledger(code=None, since=since_ms)
        total = 0.0
        for r in rows:
            info = r.get("info") or {}
            if str(info.get("instId") or "") != symbol:
                continue
            if str(info.get("subType") or "") in {"realized_pnl", "204"}:
                total += float(info.get("pnl") or info.get("amount") or 0.0)
        return total

    async def fetch_klines(
        self, symbol: str, tf: str, *, end_ms: int | None = None, limit: int = 500
    ) -> list[dict]:
        params = {}
        if end_ms:
            params["until"] = end_ms
        rows = await self.client.fetch_ohlcv(symbol, timeframe=tf, limit=limit, params=params)
        return [
            {
                "open_time": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
                "closed": True,
            }
            for r in rows
        ]

    async def load_exchange_info(self) -> list[InstrumentInfo]:
        markets = await self.client.load_markets()
        out: list[InstrumentInfo] = []
        for ccxt_sym, m in markets.items():
            if not m.get("swap") or m.get("quote") != "USDT":
                continue
            native = m.get("id") or ccxt_sym  # e.g. "BTC-USDT-SWAP"
            precision = m.get("precision") or {}
            limits = m.get("limits") or {}
            tick = float(precision.get("price") or 0)
            lot = float(precision.get("amount") or 0)
            min_qty = float((limits.get("amount") or {}).get("min") or 0)
            min_notional = float((limits.get("cost") or {}).get("min") or 0)
            out.append(
                InstrumentInfo(
                    exchange="okx",
                    symbol=native,
                    base=m.get("base") or "",
                    quote="USDT",
                    contract_type="usdt-perp",
                    tick_size=tick,
                    lot_size=lot,
                    min_qty=min_qty,
                    min_notional=min_notional,
                    ccxt_symbol=ccxt_sym,
                    active=bool(m.get("active", True)),
                )
            )
        return out

    def _ensure_pro(self) -> None:
        if ccxt_pro is None:  # pragma: no cover
            raise RuntimeError("ccxt.pro is required for streaming")
        if self._pro_client is None:
            self._pro_client = ccxt_pro.okx(
                {
                    "apiKey": self.api_key,
                    "secret": self.api_secret,
                    "password": self.passphrase,
                    "enableRateLimit": True,
                    "options": {"defaultType": "swap"},
                }
            )
            if self.testnet:
                self._pro_client.set_sandbox_mode(True)

    async def iter_user_data(self) -> AsyncIterator[FillEvent]:
        self._ensure_pro()
        while True:
            try:
                orders = await self._pro_client.watch_orders()
                for o in orders:
                    yield _ccxt_order_to_fill("okx", o)
            except Exception as e:
                log.warning("OKX watch_orders error: %s; reconnect in 3s", e)
                await asyncio.sleep(3)

    async def iter_klines(
        self, subs: list[tuple[str, str]]
    ) -> AsyncIterator[KlineMsg]:
        self._ensure_pro()
        queue: asyncio.Queue[KlineMsg] = asyncio.Queue(maxsize=4096)
        tasks: list[asyncio.Task] = []

        async def _watch(native: str, tf: str) -> None:
            ccxt_sym = to_ccxt_symbol("okx", native)
            while True:
                try:
                    bars = await self._pro_client.watch_ohlcv(ccxt_sym, tf)
                    for b in bars or []:
                        await queue.put(
                            KlineMsg(
                                exchange="okx",
                                symbol=native,
                                tf=tf,
                                open_time=int(b[0]),
                                close_time=int(b[0]) + _tf_ms(tf) - 1,
                                open=float(b[1]),
                                high=float(b[2]),
                                low=float(b[3]),
                                close=float(b[4]),
                                volume=float(b[5]),
                                closed=False,
                            )
                        )
                except Exception as e:
                    log.warning("OKX watch_ohlcv %s %s error: %s", native, tf, e)
                    await asyncio.sleep(1)

        for native, tf in subs:
            tasks.append(asyncio.create_task(_watch(native, tf)))
        try:
            while True:
                yield await queue.get()
        finally:
            for t in tasks:
                t.cancel()

    async def close(self) -> None:
        try:
            await self.client.close()
        except Exception:
            pass
        if self._pro_client is not None:
            try:
                await self._pro_client.close()
            except Exception:
                pass


def _ccxt_order_to_fill(exchange: str, o: dict) -> FillEvent:
    status_map = {"closed": "filled", "canceled": "canceled", "open": "new", "expired": "canceled"}
    filled = float(o.get("filled") or 0.0)
    remaining = float(o.get("remaining") or 0.0)
    base_status = status_map.get(str(o.get("status") or ""), "new")
    if base_status == "new" and filled > 0 and remaining > 0:
        base_status = "partially_filled"
    info = o.get("info") or {}
    realized = float(info.get("fillPnl") or info.get("rPnl") or 0.0)
    return FillEvent(
        exchange=exchange,
        symbol=str((o.get("info") or {}).get("instId")
                    or (o.get("info") or {}).get("symbol")
                    or o.get("symbol") or ""),
        exchange_order_id=str(o.get("id") or ""),
        status=base_status,
        side=str(o.get("side") or "").lower(),
        filled_qty=filled,
        avg_price=float(o.get("average") or o.get("price") or 0.0),
        realized_pnl=realized,
        timestamp_ms=int(o.get("timestamp") or int(time.time() * 1000)),
    )


def _tf_ms(tf: str) -> int:
    n = int(tf[:-1])
    u = tf[-1]
    return n * {"s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}[u]
