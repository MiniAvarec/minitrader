"""Exness broker — MetaTrader 5 via the `mt5linux` RPyC bridge.

Exness exposes **no public REST/WebSocket trading API**. The only programmatic
access is MetaTrader 5. The official `MetaTrader5` package is Windows-native,
synchronous and single-connection, so we run an MT5 terminal (logged into the
Exness account) inside the `mt5gateway` sidecar and talk to it from here with
the `mt5linux` RPyC client.

Design mirrors the IBKR broker (brokers/ibkr.py):
- Non-ccxt; gateway holds the session, this class attaches to it.
- No user-data websocket → fills and klines are polled (like IBKR).
- Account currency is USD (not USDT) — `usdt_balance()` keeps the ABC name.
- No global exchange-info → curated `exness_universe.yaml`, reconciled with
  the live terminal's per-account symbol suffixes (e.g. `EURUSDm`).

All MT5 calls are blocking and the terminal is single-threaded, so every call
goes through `_call()` which serializes on an asyncio.Lock and offloads to a
worker thread.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import yaml

from app.brokers.base import Broker, FillEvent, InstrumentInfo, KlineMsg

log = logging.getLogger("brokers.exness")


# Project tf -> MT5 TIMEFRAME_* constant name. Resolved against the live client
# (the ints are stable across MT5 builds but we read them off the bridge).
_TF_NAME = {
    "1m": "TIMEFRAME_M1",
    "3m": "TIMEFRAME_M3",
    "5m": "TIMEFRAME_M5",
    "15m": "TIMEFRAME_M15",
    "30m": "TIMEFRAME_M30",
    "1h": "TIMEFRAME_H1",
    "2h": "TIMEFRAME_H2",
    "4h": "TIMEFRAME_H4",
    "1d": "TIMEFRAME_D1",
}

_TF_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1d": 86400,
}


def _universe_path() -> Path:
    return Path(__file__).with_name("exness_universe.yaml")


def _load_universe() -> list[dict]:
    p = _universe_path()
    if not p.exists():
        return []
    with p.open() as f:
        doc = yaml.safe_load(f) or {}
    return doc.get("symbols") or []


class ExnessBroker(Broker):
    exchange_id = "exness"

    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        *,
        bridge_host: str = "mt5gateway",
        bridge_port: int = 18812,
        testnet: bool = True,
    ):
        # Lazy-import so the rest of the codebase doesn't need mt5linux when no
        # Exness key is configured (mirrors ibkr.py's ib_insync lazy import).
        from mt5linux import MetaTrader5  # noqa: F401  (import-time availability check)

        self._MetaTrader5 = MetaTrader5
        self.login = int(login) if login else 0
        self.password = password or ""
        self.server = server or ""
        self.bridge_host = bridge_host
        self.bridge_port = int(bridge_port)
        self.testnet = testnet  # informational; demo vs live is the server name
        self._mt5: Any | None = None
        self._connected = False
        self._lock = asyncio.Lock()
        # symbol -> resolved per-account name (handles EURUSD -> EURUSDm)
        self._symbol_cache: dict[str, str] = {}
        self._info_cache: dict[str, InstrumentInfo] = {}

    # ----- connection / call plumbing -----

    async def _call(self, fn_name: str, *args, **kwargs):
        """Serialize + offload a blocking MT5 call to a worker thread."""
        await self._ensure_connected()
        async with self._lock:
            fn = getattr(self._mt5, fn_name)
            return await asyncio.to_thread(fn, *args, **kwargs)

    async def _const(self, name: str, default: int) -> int:
        await self._ensure_connected()
        try:
            return int(getattr(self._mt5, name))
        except Exception:
            return default

    async def _ensure_connected(self) -> None:
        if self._connected and self._mt5 is not None:
            return
        async with self._lock:
            if self._connected and self._mt5 is not None:
                return
            log.info(
                "exness connect bridge=%s:%s server=%s login=%s",
                self.bridge_host,
                self.bridge_port,
                self.server or "(gateway default)",
                self.login or "(gateway session)",
            )
            mt5 = self._MetaTrader5(host=self.bridge_host, port=self.bridge_port)

            def _init() -> bool:
                if not mt5.initialize():
                    return False
                # When per-user credentials are supplied (a keyed user), log in
                # explicitly. The public path (instruments_refresh passes empty
                # creds) just attaches to whatever the gateway is logged into.
                if self.login and self.password and self.server:
                    if not mt5.login(
                        self.login, password=self.password, server=self.server
                    ):
                        return False
                return mt5.account_info() is not None

            ok = await asyncio.to_thread(_init)
            if not ok:
                err = await asyncio.to_thread(mt5.last_error)
                raise RuntimeError(f"MT5 initialize/login failed: {err}")
            self._mt5 = mt5
            self._connected = True

    async def _resolve_symbol(self, symbol: str) -> str:
        """Map a stored symbol to the account's actual symbol name and select it.

        Exness account types append a suffix (e.g. `EURUSDm`). If the exact
        name isn't found we scan once for a `<symbol>*` match.
        """
        if symbol in self._symbol_cache:
            return self._symbol_cache[symbol]
        info = await self._call("symbol_info", symbol)
        name = symbol
        if info is None:
            allsyms = await self._call("symbols_get") or []
            cand = None
            for s in allsyms:
                sn = str(getattr(s, "name", ""))
                if sn == symbol or sn.startswith(symbol):
                    cand = sn
                    if sn == symbol:
                        break
            if cand is None:
                raise RuntimeError(f"exness symbol not found: {symbol}")
            name = cand
        await self._call("symbol_select", name, True)
        self._symbol_cache[symbol] = name
        return name

    # ----- core ops -----

    async def usdt_balance(self) -> float:
        """Account equity in the account currency (USD for Exness, not USDT).

        Name kept for `Broker` ABC compatibility — same convention as IBKR.
        """
        acct = await self._call("account_info")
        if acct is None:
            return 0.0
        try:
            return float(acct.equity)
        except Exception:
            return 0.0

    async def positions(self) -> list[dict]:
        raw = await self._call("positions_get") or []
        pos_buy = await self._const("POSITION_TYPE_BUY", 0)
        out: list[dict] = []
        for p in raw:
            try:
                vol = float(getattr(p, "volume", 0.0) or 0.0)
                if vol == 0:
                    continue
                sym = str(getattr(p, "symbol", ""))
                entry = float(getattr(p, "price_open", 0.0) or 0.0)
                mark = float(getattr(p, "price_current", 0.0) or 0.0)
                profit = float(getattr(p, "profit", 0.0) or 0.0)
                ptype = int(getattr(p, "type", 0) or 0)
                side = "long" if ptype == pos_buy else "short"
                csize = await self._contract_size(sym)
                qty_units = vol * csize
                out.append(
                    {
                        "symbol": sym,
                        "side": side,
                        "contracts": qty_units,
                        "notional": qty_units * mark,
                        "entry_price": entry,
                        "mark_price": mark,
                        "unrealized_pnl": profit,
                        "leverage": 1.0,
                    }
                )
            except Exception as e:
                log.warning("exness positions parse error: %s", e)
        return out

    async def _contract_size(self, resolved_symbol: str) -> float:
        info = await self._call("symbol_info", resolved_symbol)
        try:
            return float(getattr(info, "trade_contract_size", 1.0) or 1.0)
        except Exception:
            return 1.0

    async def mark_price(self, symbol: str) -> float:
        name = await self._resolve_symbol(symbol)
        tick = await self._call("symbol_info_tick", name)
        if tick is None:
            return 0.0
        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        last = float(getattr(tick, "last", 0.0) or 0.0)
        return last or bid or ask

    async def order_book(self, symbol: str, *, limit: int = 20) -> dict:
        # MT5 market depth requires market_book_add and is unreliable on retail
        # FX feeds — return top-of-book from the tick (L1 only).
        name = await self._resolve_symbol(symbol)
        tick = await self._call("symbol_info_tick", name)
        if tick is None:
            return {"bids": [], "asks": []}
        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        vol = float(getattr(tick, "volume", 0.0) or 0.0)
        return {
            "bids": [[bid, vol]] if bid > 0 else [],
            "asks": [[ask, vol]] if ask > 0 else [],
        }

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
        """Send an MT5 market deal.

        `qty` arrives in BASE UNITS (the executor's convention). MT5 trades in
        lots, so we convert: lots = qty / trade_contract_size, snapped to
        volume_step and clamped to [volume_min, volume_max].

        `reduce_only` closes against the opposing net exposure for the symbol
        (works for both netting and hedging accounts: we cap volume to the
        open opposing volume and, on hedging accounts, target a position
        ticket).
        """
        name = await self._resolve_symbol(symbol)
        sinfo = await self._call("symbol_info", name)
        if sinfo is None:
            return {"id": "", "status": "rejected", "reason": "unknown symbol"}

        csize = float(getattr(sinfo, "trade_contract_size", 1.0) or 1.0)
        vstep = float(getattr(sinfo, "volume_step", 0.01) or 0.01)
        vmin = float(getattr(sinfo, "volume_min", 0.01) or 0.01)
        vmax = float(getattr(sinfo, "volume_max", 1e9) or 1e9)
        digits = int(getattr(sinfo, "digits", 5) or 5)

        lots = (qty / csize) if csize else qty
        # Snap to the broker's volume step, then clamp.
        lots = round(round(lots / vstep) * vstep, 8)
        lots = max(vmin, min(lots, vmax))

        buy = await self._const("ORDER_TYPE_BUY", 0)
        sell = await self._const("ORDER_TYPE_SELL", 1)
        act_deal = await self._const("TRADE_ACTION_DEAL", 1)
        time_gtc = await self._const("ORDER_TIME_GTC", 0)
        fill_ioc = await self._const("ORDER_FILLING_IOC", 1)
        pos_buy = await self._const("POSITION_TYPE_BUY", 0)
        retcode_done = await self._const("TRADE_RETCODE_DONE", 10009)

        is_buy = side.lower() == "buy"
        order_type = buy if is_buy else sell

        target_ticket = None
        if reduce_only:
            open_pos = await self._call("positions_get", symbol=name) or []
            opp_vol = 0.0
            for p in open_pos:
                ptype = int(getattr(p, "type", 0) or 0)
                # A BUY order reduces SHORT positions; SELL reduces LONG.
                is_short = ptype != pos_buy
                if (is_buy and is_short) or ((not is_buy) and not is_short):
                    opp_vol += float(getattr(p, "volume", 0.0) or 0.0)
                    if target_ticket is None:
                        target_ticket = int(getattr(p, "ticket", 0) or 0)
            if opp_vol <= 0:
                return {"id": "", "status": "skipped", "reason": "no position to reduce"}
            lots = max(vmin, min(lots, round(round(opp_vol / vstep) * vstep, 8)))

        tick = await self._call("symbol_info_tick", name)
        price = float(getattr(tick, "ask", 0.0) if is_buy else getattr(tick, "bid", 0.0))

        request: dict = {
            "action": act_deal,
            "symbol": name,
            "volume": float(lots),
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": 770001,  # tags minitrader-originated deals
            "comment": "minitrader",
            "type_time": time_gtc,
            "type_filling": fill_ioc,
        }
        if sl:
            request["sl"] = round(float(sl), digits)
        if tp:
            request["tp"] = round(float(tp), digits)
        if target_ticket:
            request["position"] = target_ticket

        result = await self._call("order_send", request)
        if result is None:
            err = await self._call("last_error")
            return {"id": "", "status": "rejected", "reason": str(err)}
        retcode = int(getattr(result, "retcode", -1) or -1)
        order_id = int(getattr(result, "order", 0) or 0)
        status = "submitted" if retcode == retcode_done else "rejected"
        return {
            "id": str(order_id),
            "status": status,
            "retcode": retcode,
            "comment": str(getattr(result, "comment", "")),
        }

    async def fetch_realized_pnl(self, symbol: str, since_ms: int) -> float:
        name = await self._resolve_symbol(symbol)
        frm = datetime.fromtimestamp(since_ms / 1000.0, tz=timezone.utc)
        to = datetime.now(timezone.utc) + timedelta(minutes=1)
        deals = await self._call("history_deals_get", frm, to) or []
        total = 0.0
        for d in deals:
            try:
                if str(getattr(d, "symbol", "")) != name:
                    continue
                total += float(getattr(d, "profit", 0.0) or 0.0)
                total += float(getattr(d, "commission", 0.0) or 0.0)
                total += float(getattr(d, "swap", 0.0) or 0.0)
            except Exception:
                continue
        return total

    async def fetch_klines(
        self, symbol: str, tf: str, *, end_ms: int | None = None, limit: int = 500
    ) -> list[dict]:
        if tf not in _TF_NAME:
            raise ValueError(f"unsupported exness timeframe: {tf}")
        name = await self._resolve_symbol(symbol)
        mt5_tf = await self._const(_TF_NAME[tf], 0)
        if end_ms:
            end_dt = datetime.fromtimestamp(end_ms / 1000.0, tz=timezone.utc)
            rates = await self._call("copy_rates_from", name, mt5_tf, end_dt, limit)
        else:
            rates = await self._call("copy_rates_from_pos", name, mt5_tf, 0, limit)
        out: list[dict] = []
        for r in rates if rates is not None else []:
            try:
                # numpy rates rows expose named fields via index access.
                ot = int(r["time"]) * 1000
                out.append(
                    {
                        "open_time": ot,
                        "open": float(r["open"]),
                        "high": float(r["high"]),
                        "low": float(r["low"]),
                        "close": float(r["close"]),
                        "volume": float(
                            r["real_volume"] if r["real_volume"] else r["tick_volume"]
                        ),
                        "closed": True,
                    }
                )
            except Exception as e:
                log.debug("exness kline row parse skipped: %s", e)
        if limit and len(out) > limit:
            out = out[-limit:]
        return out

    async def load_exchange_info(self) -> list[InstrumentInfo]:
        universe = _load_universe()
        if not universe:
            log.warning("exness_universe.yaml is empty; no instruments loaded")
            return []
        out: list[InstrumentInfo] = []
        for entry in universe:
            try:
                want = str(entry["symbol"])
                ctype = str(entry.get("contract_type", "forex"))
                try:
                    name = await self._resolve_symbol(want)
                except Exception as e:
                    log.info("exness universe: %s unavailable on account (%s)", want, e)
                    continue
                sinfo = await self._call("symbol_info", name)
                if sinfo is None:
                    continue
                tick_size = float(
                    getattr(sinfo, "trade_tick_size", 0.0)
                    or getattr(sinfo, "point", 0.0)
                    or 0.0
                )
                lot_size = float(getattr(sinfo, "volume_step", 0.01) or 0.01)
                min_qty = float(getattr(sinfo, "volume_min", 0.01) or 0.01)
                csize = float(getattr(sinfo, "trade_contract_size", 1.0) or 1.0)
                quote = str(
                    getattr(sinfo, "currency_profit", "")
                    or entry.get("quote", "USD")
                )
                base = str(entry.get("base") or want[:3])
                info = InstrumentInfo(
                    exchange="exness",
                    symbol=name,
                    base=base,
                    quote=quote,
                    contract_type=ctype,
                    tick_size=tick_size,
                    # lot/min are MT5 lots; the executor's qty is base units and
                    # is converted via contract_size in place_market.
                    lot_size=lot_size * csize,
                    min_qty=min_qty * csize,
                    min_notional=float(entry.get("min_notional", 0.0)),
                    ccxt_symbol="",
                    active=bool(getattr(sinfo, "visible", True)),
                    contract_size=csize,
                )
                out.append(info)
                self._info_cache[name] = info
            except Exception as e:
                log.warning("exness universe entry failed (%s): %s", entry, e)
        return out

    async def iter_user_data(self) -> AsyncIterator[FillEvent]:
        """Poll closed deals and surface them as FillEvents (no MT5 websocket).

        Mirrors the IBKR polling model; the REST-fallback tracker
        (orders/tracker.py) covers gaps the same way it does for IBKR.
        """
        await self._ensure_connected()
        queue: asyncio.Queue[FillEvent] = asyncio.Queue(maxsize=2048)
        poll_s = int(os.environ.get("EXNESS_FILL_POLL_S", "4"))

        async def _poll() -> None:
            seen: set[int] = set()
            cursor = datetime.now(timezone.utc) - timedelta(minutes=2)
            deal_buy = await self._const("DEAL_TYPE_BUY", 0)
            while True:
                await asyncio.sleep(poll_s)
                try:
                    to = datetime.now(timezone.utc) + timedelta(minutes=1)
                    deals = await self._call("history_deals_get", cursor, to) or []
                except Exception as e:
                    log.warning("exness fill poll error: %s", e)
                    continue
                newest = cursor
                for d in deals:
                    try:
                        ticket = int(getattr(d, "ticket", 0) or 0)
                        if ticket in seen or ticket == 0:
                            continue
                        order_id = int(getattr(d, "order", 0) or 0)
                        if order_id == 0:
                            continue  # balance/credit ops, not order fills
                        seen.add(ticket)
                        sym = str(getattr(d, "symbol", ""))
                        dtype = int(getattr(d, "type", 0) or 0)
                        vol = float(getattr(d, "volume", 0.0) or 0.0)
                        price = float(getattr(d, "price", 0.0) or 0.0)
                        pnl = (
                            float(getattr(d, "profit", 0.0) or 0.0)
                            + float(getattr(d, "commission", 0.0) or 0.0)
                            + float(getattr(d, "swap", 0.0) or 0.0)
                        )
                        ts = int(getattr(d, "time_msc", 0) or 0)
                        if ts == 0:
                            ts = int(getattr(d, "time", 0) or 0) * 1000
                        csize = await self._contract_size(sym) if sym else 1.0
                        queue.put_nowait(
                            FillEvent(
                                exchange="exness",
                                symbol=sym,
                                exchange_order_id=str(order_id),
                                status="filled",
                                side="buy" if dtype == deal_buy else "sell",
                                # report in base units to match place_market input
                                filled_qty=vol * csize,
                                avg_price=price,
                                realized_pnl=pnl,
                                timestamp_ms=ts,
                            )
                        )
                        d_dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
                        if d_dt > newest:
                            newest = d_dt
                    except Exception as e:
                        log.debug("exness deal parse skipped: %s", e)
                # Re-scan a small overlap window to avoid missing late writes.
                cursor = newest - timedelta(seconds=poll_s * 2)

        task = asyncio.create_task(_poll())
        try:
            while True:
                yield await queue.get()
        finally:
            task.cancel()

    async def iter_klines(
        self, subs: list[tuple[str, str]]
    ) -> AsyncIterator[KlineMsg]:
        """Poll the latest closed bar per (symbol, tf) at each bar boundary
        (identical strategy to IBKRBroker.iter_klines)."""
        await self._ensure_connected()
        queue: asyncio.Queue[KlineMsg] = asyncio.Queue(maxsize=2048)

        async def _poll(symbol: str, tf: str) -> None:
            tf_s = _TF_SECONDS[tf]
            last_open: int | None = None
            while True:
                now = datetime.now(timezone.utc).timestamp()
                next_boundary = (int(now // tf_s) + 1) * tf_s + 5
                await asyncio.sleep(max(1.0, next_boundary - now))
                try:
                    bars = await self.fetch_klines(symbol, tf, limit=2)
                except Exception as e:
                    log.warning(
                        "exness poll fetch_klines failed %s %s: %s", symbol, tf, e
                    )
                    continue
                for b in bars:
                    ot = int(b["open_time"])
                    if last_open is not None and ot <= last_open:
                        continue
                    queue.put_nowait(
                        KlineMsg(
                            exchange="exness",
                            symbol=symbol,
                            tf=tf,
                            open_time=ot,
                            close_time=ot + tf_s * 1000,
                            open=float(b["open"]),
                            high=float(b["high"]),
                            low=float(b["low"]),
                            close=float(b["close"]),
                            volume=float(b["volume"]),
                            closed=True,
                        )
                    )
                    last_open = ot

        tasks = [asyncio.create_task(_poll(s, t)) for s, t in subs]
        try:
            while True:
                yield await queue.get()
        finally:
            for t in tasks:
                t.cancel()

    async def close(self) -> None:
        if self._connected and self._mt5 is not None:
            try:
                await asyncio.to_thread(self._mt5.shutdown)
            except Exception as e:
                log.warning("exness shutdown error: %s", e)
            finally:
                self._connected = False
                self._mt5 = None
