"""Async Binance USDT-M Futures broker (ccxt + ccxt.pro for WS).

Implements the multi-exchange `Broker` interface from base.py. User-data fills
come via Binance ListenKey + raw WS at `wss://[fstream-testnet|fstream].binance.com/ws/<key>`;
public klines come via ccxt.pro `watch_ohlcv`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

import ccxt.async_support as ccxt_async
import httpx

try:
    import ccxt.pro as ccxt_pro
except Exception:  # pragma: no cover - ccxt.pro may be packaged separately
    ccxt_pro = None  # type: ignore[assignment]

import websockets

from app.brokers.base import (
    Broker,
    FillEvent,
    InstrumentInfo,
    KlineMsg,
)


log = logging.getLogger("brokers.binance")


_REST_LIVE = "https://fapi.binance.com"
_REST_TESTNET = "https://testnet.binancefuture.com"
_WS_LIVE = "wss://fstream.binance.com/ws"
_WS_TESTNET = "wss://stream.binancefuture.com/ws"


class BinanceBroker(Broker):
    exchange_id = "binance"

    def __init__(self, api_key: str, api_secret: str, *, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.client = ccxt_async.binanceusdm(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
            }
        )
        if testnet:
            self.client.set_sandbox_mode(True)
        self._pro_client = None  # lazy-initialised in iter_klines
        self._listen_key: str | None = None

    # ----- core ops -----

    async def usdt_balance(self) -> float:
        bal = await self.client.fetch_balance()
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
        params: dict = {}
        if reduce_only:
            params["reduceOnly"] = True
        order = await self.client.create_order(symbol, "market", side, qty, None, params)
        opp = "sell" if side == "buy" else "buy"
        if sl:
            await self.client.create_order(
                symbol, "STOP_MARKET", opp, qty, None,
                {"stopPrice": sl, "reduceOnly": True, "workingType": "MARK_PRICE"},
            )
        if tp:
            await self.client.create_order(
                symbol, "TAKE_PROFIT_MARKET", opp, qty, None,
                {"stopPrice": tp, "reduceOnly": True, "workingType": "MARK_PRICE"},
            )
        return order

    async def fetch_realized_pnl(self, symbol: str, since_ms: int) -> float:
        # Binance income endpoint: /fapi/v1/income?incomeType=REALIZED_PNL&symbol=...&startTime=...
        rows = await self.client.fapiprivate_get_income(
            {"symbol": symbol, "incomeType": "REALIZED_PNL", "startTime": since_ms}
        )
        return float(sum(float(r.get("income") or 0.0) for r in rows))

    async def fetch_klines(
        self, symbol: str, tf: str, *, end_ms: int | None = None, limit: int = 500
    ) -> list[dict]:
        # ccxt accepts the unified symbol; symbol here is exchange-native, caller converts.
        params = {"endTime": end_ms} if end_ms else {}
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
        base = _REST_TESTNET if self.testnet else _REST_LIVE
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.get(f"{base}/fapi/v1/exchangeInfo")
            r.raise_for_status()
            doc = r.json()
        out: list[InstrumentInfo] = []
        for s in doc.get("symbols", []):
            if s.get("contractType") != "PERPETUAL":
                continue
            if s.get("quoteAsset") != "USDT":
                continue
            tick = lot = min_qty = min_notional = 0.0
            for f in s.get("filters", []):
                t = f.get("filterType")
                if t == "PRICE_FILTER":
                    tick = float(f.get("tickSize") or 0)
                elif t == "LOT_SIZE":
                    lot = float(f.get("stepSize") or 0)
                    min_qty = float(f.get("minQty") or 0)
                elif t == "MIN_NOTIONAL":
                    min_notional = float(f.get("notional") or f.get("minNotional") or 0)
            native = s["symbol"]
            base_ccy = s["baseAsset"]
            quote_ccy = s["quoteAsset"]
            out.append(
                InstrumentInfo(
                    exchange="binance",
                    symbol=native,
                    base=base_ccy,
                    quote=quote_ccy,
                    contract_type="usdt-perp",
                    tick_size=tick,
                    lot_size=lot,
                    min_qty=min_qty,
                    min_notional=min_notional,
                    ccxt_symbol=f"{base_ccy}/{quote_ccy}:{quote_ccy}",
                    active=s.get("status") == "TRADING",
                )
            )
        return out

    # ----- streaming -----

    async def _get_listen_key(self) -> str:
        base = _REST_TESTNET if self.testnet else _REST_LIVE
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.post(
                f"{base}/fapi/v1/listenKey",
                headers={"X-MBX-APIKEY": self.api_key},
            )
            r.raise_for_status()
            return r.json()["listenKey"]

    async def _keepalive_listen_key(self) -> None:
        base = _REST_TESTNET if self.testnet else _REST_LIVE
        async with httpx.AsyncClient(timeout=10) as http:
            await http.put(
                f"{base}/fapi/v1/listenKey",
                headers={"X-MBX-APIKEY": self.api_key},
            )

    async def iter_user_data(self) -> AsyncIterator[FillEvent]:
        ws_base = _WS_TESTNET if self.testnet else _WS_LIVE
        while True:
            try:
                self._listen_key = await self._get_listen_key()
                url = f"{ws_base}/{self._listen_key}"
                last_keepalive = time.time()
                async with websockets.connect(url, ping_interval=180, ping_timeout=30) as ws:
                    while True:
                        if time.time() - last_keepalive > 1700:  # ~28 min
                            try:
                                await self._keepalive_listen_key()
                                last_keepalive = time.time()
                            except Exception as e:
                                log.warning("listenKey keepalive failed: %s", e)
                                break
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        except asyncio.TimeoutError:
                            continue
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue
                        if msg.get("e") != "ORDER_TRADE_UPDATE":
                            continue
                        o = msg.get("o", {})
                        status_map = {
                            "FILLED": "filled",
                            "PARTIALLY_FILLED": "partially_filled",
                            "CANCELED": "canceled",
                            "EXPIRED": "canceled",
                            "REJECTED": "rejected",
                            "NEW": "new",
                        }
                        yield FillEvent(
                            exchange="binance",
                            symbol=str(o.get("s") or ""),
                            exchange_order_id=str(o.get("i") or ""),
                            status=status_map.get(str(o.get("X") or ""), "new"),
                            side=str(o.get("S") or "").lower(),
                            filled_qty=float(o.get("z") or 0.0),
                            avg_price=float(o.get("ap") or 0.0),
                            realized_pnl=float(o.get("rp") or 0.0),
                            timestamp_ms=int(msg.get("E") or 0),
                        )
            except Exception as e:
                log.warning("user-data WS error: %s; reconnect in 3s", e)
                await asyncio.sleep(3)

    async def iter_klines(
        self, subs: list[tuple[str, str]]
    ) -> AsyncIterator[KlineMsg]:
        if ccxt_pro is None:  # pragma: no cover
            raise RuntimeError("ccxt.pro is required for streaming")
        if self._pro_client is None:
            self._pro_client = ccxt_pro.binanceusdm(
                {
                    "apiKey": self.api_key,
                    "secret": self.api_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "future"},
                }
            )
            if self.testnet:
                self._pro_client.set_sandbox_mode(True)
        # ccxt.pro watch_ohlcv is per-(symbol, tf); fan out via tasks → asyncio.Queue.
        queue: asyncio.Queue[KlineMsg] = asyncio.Queue(maxsize=4096)
        tasks: list[asyncio.Task] = []
        from app.brokers.base import to_ccxt_symbol, from_ccxt_symbol

        async def _watch(native: str, tf: str) -> None:
            ccxt_sym = to_ccxt_symbol("binance", native)
            while True:
                try:
                    bars = await self._pro_client.watch_ohlcv(ccxt_sym, tf)
                    if not bars:
                        continue
                    for b in bars:
                        # ccxt.pro yields the in-progress bar each tick; mark `closed=False`
                        # except for the most recent settled bar (the dedupe layer handles
                        # the rest).
                        await queue.put(
                            KlineMsg(
                                exchange="binance",
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
                    log.warning("watch_ohlcv %s %s error: %s", native, tf, e)
                    await asyncio.sleep(1)

        for native, tf in subs:
            tasks.append(asyncio.create_task(_watch(native, tf)))
        try:
            while True:
                msg = await queue.get()
                yield msg
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


def _tf_ms(tf: str) -> int:
    n = int(tf[:-1])
    u = tf[-1]
    return n * {"s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}[u]
