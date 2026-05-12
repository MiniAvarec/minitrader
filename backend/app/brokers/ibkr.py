"""Interactive Brokers (IBKR) broker — TWS / IB Gateway via ib_insync.

Implements the multi-exchange `Broker` interface from base.py for non-crypto
markets (stocks, ETFs, futures, options, forex). Connects to a locally-running
TWS or IB Gateway on `host:port` with a unique `client_id`.

ib_insync notes:
- Use `await IB().connectAsync(host, port, clientId)` from inside FastAPI's
  running loop. Do NOT call `util.startLoop()` (that's a Jupyter helper).
- ib_insync's reqXxxAsync methods return regular coroutines; event-style APIs
  (execDetailsEvent, orderStatusEvent, disconnectedEvent) are handled in
  phases 4/6.
- IBKR has no global exchange-info; we lazy-resolve contracts and ship a
  curated universe yaml that the `instruments` worker pre-seeds.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import yaml

from app.brokers.base import (
    Broker,
    FillEvent,
    InstrumentInfo,
    KlineMsg,
    decode_ibkr_symbol,
)


log = logging.getLogger("brokers.ibkr")


# ---- bar-size mapping ----
# IBKR's reqHistoricalData accepts a `barSizeSetting` like "5 mins"; we map
# from the project's own tf strings.
_BAR_SIZE = {
    "1m": "1 min",
    "3m": "3 mins",
    "5m": "5 mins",
    "15m": "15 mins",
    "30m": "30 mins",
    "1h": "1 hour",
    "2h": "2 hours",
    "4h": "4 hours",
    "1d": "1 day",
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

# Routing exchanges that signal forex pairs (CASH contracts) vs stock contracts
# in the simple 3-part symbol case (X.Y.Z without expiry/strike).
_FX_ROUTING = {"IDEALPRO", "FXSUBPIP"}


def _bar_size(tf: str) -> str:
    if tf not in _BAR_SIZE:
        raise ValueError(f"unsupported IBKR timeframe: {tf}")
    return _BAR_SIZE[tf]


def _duration_str(tf: str, limit: int) -> str:
    """Build a `durationStr` covering `limit` bars of `tf`, with safety pad."""
    seconds = _TF_SECONDS[tf] * max(limit, 1)
    # Generous pad to cover RTH/non-RTH gaps for intraday data.
    seconds = int(seconds * 1.5)
    # IBKR caps: 86400 S for intraday minute bars, 2 Y for daily.
    if tf == "1d":
        days = max(1, (seconds // 86400) + 1)
        return f"{min(days, 730)} D"
    if seconds <= 86400:
        return f"{seconds} S"
    days = (seconds // 86400) + 1
    return f"{min(days, 60)} D"


_STATUS_MAP = {
    "Filled": "filled",
    "PartiallyFilled": "partially_filled",
    "PreSubmitted": "new",
    "Submitted": "new",
    "PendingSubmit": "new",
    "PendingCancel": "new",
    "Cancelled": "canceled",
    "Inactive": "canceled",
    "ApiCancelled": "canceled",
}


def _map_order_status(s: str) -> str:
    return _STATUS_MAP.get(str(s), "new")


def _is_within_trading_hours(hours: str, tz_name: str) -> bool:
    """Parse IBKR's tradingHours string and check if now() falls in a window.

    Format: `YYYYMMDD:HHMM-YYYYMMDD:HHMM;YYYYMMDD:CLOSED;...`
    """
    if not hours:
        return True
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)
    today_key = now.strftime("%Y%m%d")
    for seg in hours.split(";"):
        seg = seg.strip()
        if not seg or "CLOSED" in seg:
            continue
        try:
            start_raw, end_raw = seg.split("-")
            start_day, start_time = start_raw.split(":")
            end_day, end_time = end_raw.split(":")
            if start_day != today_key and end_day != today_key:
                continue
            start_dt = datetime.strptime(
                f"{start_day}{start_time}", "%Y%m%d%H%M"
            ).replace(tzinfo=tz)
            end_dt = datetime.strptime(
                f"{end_day}{end_time}", "%Y%m%d%H%M"
            ).replace(tzinfo=tz)
            if start_dt <= now <= end_dt:
                return True
        except Exception:
            continue
    return False


def _universe_path() -> Path:
    return Path(__file__).with_name("ibkr_universe.yaml")


def _load_universe() -> list[dict]:
    p = _universe_path()
    if not p.exists():
        return []
    with p.open() as f:
        doc = yaml.safe_load(f) or {}
    return doc.get("contracts") or []


class IBKRBroker(Broker):
    exchange_id = "ibkr"

    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        account: str | None = None,
        *,
        testnet: bool = True,
    ):
        # Lazy-import ib_insync so the rest of the codebase doesn't require it
        # when no IBKR key is configured.
        from ib_insync import IB

        self.host = host
        self.port = int(port)
        self.client_id = int(client_id)
        self.account = account
        self.testnet = testnet  # informational; caller already chose the port
        self.ib = IB()
        self._connected = False
        self._contract_cache: dict[str, object] = {}  # symbol -> Contract
        # Cached InstrumentInfo from load_exchange_info (avoids re-resolving).
        self._instrument_info_cache: dict[str, InstrumentInfo] = {}

    # ----- connection -----

    async def _ensure_connected(self) -> None:
        if self._connected and self.ib.isConnected():
            return
        log.info(
            "ibkr connect host=%s port=%s clientId=%s account=%s",
            self.host,
            self.port,
            self.client_id,
            self.account,
        )
        await self.ib.connectAsync(self.host, self.port, clientId=self.client_id)
        # Allow delayed (15-min) data for users without market-data
        # subscriptions. Real-time data still flows if entitled.
        try:
            self.ib.reqMarketDataType(int(os.environ.get("IBKR_MARKET_DATA_TYPE", "3")))
        except Exception as e:
            log.warning("ibkr reqMarketDataType failed: %s", e)
        # On unexpected disconnect, attempt to reconnect in the background.
        # ib_insync fires `disconnectedEvent` once with no arguments. The
        # `+=` operator subscribes the handler; idempotent across reconnects
        # because we filter for already-attached handlers.
        if not getattr(self, "_disc_handler_attached", False):
            self.ib.disconnectedEvent += self._on_disconnected
            self._disc_handler_attached = True
        self._connected = True

    def _on_disconnected(self) -> None:
        log.warning("ibkr disconnected; scheduling reconnect")
        self._connected = False
        try:
            asyncio.get_running_loop().create_task(self._reconnect_loop())
        except RuntimeError:
            # No running loop — let the next _ensure_connected handle it lazily.
            pass

    async def _reconnect_loop(self) -> None:
        for delay in (3, 5, 10, 20, 30):
            await asyncio.sleep(delay)
            try:
                await self.ib.connectAsync(
                    self.host, self.port, clientId=self.client_id
                )
                self._connected = True
                log.info("ibkr reconnected after %ss", delay)
                return
            except Exception as e:
                log.warning("ibkr reconnect attempt failed (%ss): %s", delay, e)
        log.error("ibkr reconnect gave up; next request will retry")

    # ----- contract resolution -----

    async def _resolve_contract(self, symbol: str):
        """Build (and cache) an ib_insync Contract from a dot-encoded symbol.

        Stock / forex disambiguation: 3-part symbols are stocks unless the
        routing exchange is a known FX venue (IDEALPRO / FXSUBPIP) in which
        case they're forex. 4-part = future. 6-part = option.
        """
        if symbol in self._contract_cache:
            return self._contract_cache[symbol]
        from ib_insync import Contract, Forex, Future, Option, Stock

        parts = decode_ibkr_symbol(symbol)
        ctype = parts.get("contract_type")
        if ctype is None:
            ctype = "forex" if parts["routing_exchange"] in _FX_ROUTING else "stock"
        if ctype == "stock":
            c = Stock(
                parts["root"],
                parts["routing_exchange"],
                parts["currency"],
            )
        elif ctype == "future":
            c = Future(
                parts["root"],
                parts["expiry"],
                parts["routing_exchange"],
                currency=parts["currency"],
            )
        elif ctype == "forex":
            # Forex pair-base ("EUR") + quote-from-currency ("USD") -> "EURUSD".
            pair = f"{parts['root']}{parts['currency']}"
            c = Forex(pair)
        elif ctype == "option":
            c = Option(
                parts["root"],
                parts["expiry"],
                parts["strike"],
                parts["right"],
                parts["routing_exchange"],
                currency=parts["currency"],
            )
        else:  # pragma: no cover - defensive
            raise ValueError(f"unknown IBKR contract_type: {ctype}")

        await self._ensure_connected()
        qualified = await self.ib.qualifyContractsAsync(c)
        if not qualified:
            raise RuntimeError(f"IBKR could not qualify contract: {symbol}")
        resolved = qualified[0]
        self._contract_cache[symbol] = resolved
        return resolved

    # ----- core ops -----

    async def usdt_balance(self) -> float:
        """Account cash balance in the account's base currency.

        Name kept for `Broker` ABC compatibility — for IBKR this is *not* USDT
        but the account's primary currency (typically USD). Callers should
        treat the returned float as "balance in account ccy".
        """
        await self._ensure_connected()
        summary = await self.ib.accountSummaryAsync(self.account or "")
        for row in summary:
            if row.tag == "TotalCashValue":
                if self.account and row.account != self.account:
                    continue
                try:
                    return float(row.value)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    async def positions(self) -> list[dict]:
        await self._ensure_connected()
        raw = await self.ib.reqPositionsAsync()
        out: list[dict] = []
        for p in raw:
            contracts = float(p.position or 0.0)
            if contracts == 0:
                continue
            contract = p.contract
            try:
                mark = await self.mark_price(self._encode_back(contract))
            except Exception:
                mark = float(p.avgCost or 0.0)
            avg_cost = float(p.avgCost or 0.0)
            side = "long" if contracts > 0 else "short"
            qty = abs(contracts)
            notional = qty * mark
            unrealized = (mark - avg_cost) * contracts
            out.append(
                {
                    "symbol": self._encode_back(contract),
                    "side": side,
                    "contracts": qty,
                    "notional": notional,
                    "entry_price": avg_cost,
                    "mark_price": mark,
                    "unrealized_pnl": unrealized,
                    "leverage": 1.0,
                }
            )
        return out

    @staticmethod
    def _encode_back(contract) -> str:
        """Best-effort re-encode an ib_insync Contract back into a dot-encoded
        symbol. Used when surfacing positions to callers."""
        # Forex
        if getattr(contract, "secType", "") == "CASH":
            return f"{contract.symbol}.{contract.exchange or 'IDEALPRO'}.{contract.currency}"
        if getattr(contract, "secType", "") == "FUT":
            return f"{contract.symbol}.{contract.exchange}.{contract.currency}.{contract.lastTradeDateOrContractMonth}"
        if getattr(contract, "secType", "") == "OPT":
            return (
                f"{contract.symbol}.{contract.exchange}.{contract.currency}."
                f"{contract.lastTradeDateOrContractMonth}.{contract.right}.{contract.strike:g}"
            )
        # Default: stock.
        return f"{contract.symbol}.{contract.exchange or 'SMART'}.{contract.currency}"

    async def mark_price(self, symbol: str) -> float:
        await self._ensure_connected()
        contract = await self._resolve_contract(symbol)
        tickers = await self.ib.reqTickersAsync(contract)
        if not tickers:
            return 0.0
        t = tickers[0]
        bid = float(t.bid) if t.bid and t.bid > 0 else 0.0
        ask = float(t.ask) if t.ask and t.ask > 0 else 0.0
        if bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        last = float(t.last) if t.last and t.last > 0 else 0.0
        if last > 0:
            return last
        close = float(t.close) if t.close and t.close > 0 else 0.0
        return close

    async def order_book(self, symbol: str, *, limit: int = 20) -> dict:
        await self._ensure_connected()
        contract = await self._resolve_contract(symbol)
        # L2 depth requires a deep-book subscription. Try it; fall back to L1.
        try:
            ticker = self.ib.reqMktDepth(contract, numRows=min(limit, 10))
            await self.ib.sleep(0.6)  # let snapshot populate
            bids = [
                {"price": float(b.price), "size": float(b.size)}
                for b in (ticker.domBids or [])[:limit]
            ]
            asks = [
                {"price": float(a.price), "size": float(a.size)}
                for a in (ticker.domAsks or [])[:limit]
            ]
            self.ib.cancelMktDepth(contract)
            if bids or asks:
                return {"bids": [[b["price"], b["size"]] for b in bids],
                        "asks": [[a["price"], a["size"]] for a in asks]}
        except Exception as e:
            log.debug("reqMktDepth fell back to L1: %s", e)
        # L1 fallback.
        tickers = await self.ib.reqTickersAsync(contract)
        if not tickers:
            return {"bids": [], "asks": []}
        t = tickers[0]
        bid = float(t.bid) if t.bid and t.bid > 0 else 0.0
        ask = float(t.ask) if t.ask and t.ask > 0 else 0.0
        bid_sz = float(getattr(t, "bidSize", 0.0) or 0.0)
        ask_sz = float(getattr(t, "askSize", 0.0) or 0.0)
        return {
            "bids": [[bid, bid_sz]] if bid > 0 else [],
            "asks": [[ask, ask_sz]] if ask > 0 else [],
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
        """Submit a market order, optionally with SL / TP bracket children.

        - sl + tp: classic bracket (parent market + child stop + child limit).
        - sl only: parent market + child stop.
        - tp only: parent market + child limit.
        - neither: plain market.

        Children are linked to the parent via parentId. IBKR transmits the
        whole group atomically only when the LAST child has `transmit=True`.

        `reduce_only` is emulated by clamping qty against the current
        position size; IBKR's API has no first-class flag.
        """
        from ib_insync import LimitOrder, MarketOrder, StopOrder

        await self._ensure_connected()
        contract = await self._resolve_contract(symbol)
        action = "BUY" if side.lower() == "buy" else "SELL"
        opposite = "SELL" if action == "BUY" else "BUY"

        if reduce_only:
            positions = await self.ib.reqPositionsAsync()
            cur = 0.0
            for p in positions:
                if p.contract.conId == getattr(contract, "conId", None):
                    cur = float(p.position or 0.0)
                    break
            qty = min(qty, abs(cur))
            if qty <= 0:
                return {"id": "", "status": "skipped", "reason": "no position to reduce"}

        has_bracket = sl is not None or tp is not None
        parent = MarketOrder(action, qty)
        if self.account:
            parent.account = self.account
        if has_bracket:
            parent.transmit = False
            parent.orderId = self.ib.client.getReqId()
        else:
            parent.transmit = True

        placed: list = []
        trade_parent = self.ib.placeOrder(contract, parent)
        placed.append(trade_parent)

        if has_bracket:
            # The LAST child must have transmit=True so IBKR submits the group.
            children = []
            if sl is not None:
                stop = StopOrder(opposite, qty, float(sl))
                stop.parentId = parent.orderId
                if self.account:
                    stop.account = self.account
                stop.orderId = self.ib.client.getReqId()
                stop.transmit = False
                children.append(stop)
            if tp is not None:
                tp_order = LimitOrder(opposite, qty, float(tp))
                tp_order.parentId = parent.orderId
                if self.account:
                    tp_order.account = self.account
                tp_order.orderId = self.ib.client.getReqId()
                tp_order.transmit = False
                children.append(tp_order)
            # Flip last child to transmit=True.
            children[-1].transmit = True
            for child in children:
                placed.append(self.ib.placeOrder(contract, child))

        # Return shape mirrors what BinanceBroker.place_market returns.
        return {
            "id": str(parent.orderId),
            "status": "submitted",
            "children": [str(t.order.orderId) for t in placed[1:]],
        }

    async def fetch_realized_pnl(self, symbol: str, since_ms: int) -> float:
        """Sum realized PnL from executions filtered by symbol since since_ms.

        IBKR's reqExecutions takes a 'YYYYMMDD HH:MM:SS' time filter.
        We pass a date-only filter (start of day in UTC) and then re-filter
        results client-side by timestamp_ms for precision.
        """
        from ib_insync import ExecutionFilter

        await self._ensure_connected()
        parts = decode_ibkr_symbol(symbol)
        root = parts["root"]
        since_dt = datetime.fromtimestamp(since_ms / 1000.0, tz=timezone.utc)
        # IBKR filter time is the *day boundary*; we widen to that day's start.
        ef = ExecutionFilter(
            symbol=root,
            time=since_dt.strftime("%Y%m%d 00:00:00"),
        )
        fills = await self.ib.reqExecutionsAsync(ef)
        total = 0.0
        for f in fills or []:
            try:
                ts_str = getattr(f.execution, "time", "")
                # ib_insync may return a datetime or a string; handle both.
                if isinstance(ts_str, datetime):
                    ts_ms = int(ts_str.timestamp() * 1000)
                else:
                    ts_ms = int(
                        datetime.strptime(str(ts_str), "%Y%m%d %H:%M:%S %Z")
                        .replace(tzinfo=timezone.utc)
                        .timestamp()
                        * 1000
                    )
            except Exception:
                ts_ms = since_ms  # keep it if we can't parse the time
            if ts_ms < since_ms:
                continue
            pnl = getattr(f.commissionReport, "realizedPNL", 0.0)
            try:
                total += float(pnl or 0.0)
            except (TypeError, ValueError):
                pass
        return total

    async def fetch_klines(
        self, symbol: str, tf: str, *, end_ms: int | None = None, limit: int = 500
    ) -> list[dict]:
        await self._ensure_connected()
        contract = await self._resolve_contract(symbol)
        end_dt = ""
        if end_ms:
            end_dt = datetime.fromtimestamp(end_ms / 1000.0, tz=timezone.utc).strftime(
                "%Y%m%d %H:%M:%S UTC"
            )
        bars = await self.ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_dt,
            durationStr=_duration_str(tf, limit),
            barSizeSetting=_bar_size(tf),
            whatToShow="TRADES",
            useRTH=False,
            formatDate=2,  # epoch seconds in `date` field
            keepUpToDate=False,
        )
        out: list[dict] = []
        tf_s = _TF_SECONDS[tf]
        for b in bars or []:
            ts = b.date
            if hasattr(ts, "timestamp"):
                open_time = int(ts.timestamp())
            else:
                open_time = int(ts)
            out.append(
                {
                    "open_time": open_time * 1000,
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": float(b.volume) if b.volume and b.volume > 0 else 0.0,
                    "closed": True,
                }
            )
        # Honor the caller's `limit` by trimming the most recent rows; IBKR's
        # durationStr→bar-count conversion is approximate.
        if limit and len(out) > limit:
            out = out[-limit:]
        return out

    async def load_exchange_info(self) -> list[InstrumentInfo]:
        await self._ensure_connected()
        universe = _load_universe()
        if not universe:
            log.warning("ibkr_universe.yaml is empty; no instruments loaded")
            return []
        from ib_insync import Forex, Future, Option, Stock

        out: list[InstrumentInfo] = []
        for entry in universe:
            try:
                ctype = entry["contract_type"]
                root = entry["root"]
                routing = entry["routing_exchange"]
                currency = entry["currency"]
                if ctype == "stock":
                    c = Stock(root, routing, currency)
                    native = f"{root}.{routing}.{currency}"
                elif ctype == "future":
                    expiry = entry["expiry"]
                    c = Future(root, expiry, routing, currency=currency)
                    native = f"{root}.{routing}.{currency}.{expiry}"
                elif ctype == "forex":
                    pair = f"{root}{currency}"
                    c = Forex(pair)
                    native = f"{root}.{routing}.{currency}"
                elif ctype == "option":
                    expiry = entry["expiry"]
                    strike = float(entry["strike"])
                    right = entry["right"]
                    c = Option(root, expiry, strike, right, routing, currency=currency)
                    native = f"{root}.{routing}.{currency}.{expiry}.{right}.{strike:g}"
                else:
                    log.warning("unknown contract_type in universe: %r", ctype)
                    continue

                details_list = await self.ib.reqContractDetailsAsync(c)
                if not details_list:
                    log.info("ibkr universe: no contract details for %s", native)
                    continue
                details = details_list[0]
                tick_size = float(getattr(details, "minTick", 0.0) or 0.0)
                # Stocks: 1-share minimum (fractionals are a feature flag); futures: 1.
                lot_size = float(entry.get("lot_size", 1.0))
                min_qty = float(entry.get("min_qty", 1.0))
                min_notional = float(entry.get("min_notional", 0.0))
                info = InstrumentInfo(
                    exchange="ibkr",
                    symbol=native,
                    base=root,
                    quote=currency,
                    contract_type=ctype,
                    tick_size=tick_size,
                    lot_size=lot_size,
                    min_qty=min_qty,
                    min_notional=min_notional,
                    ccxt_symbol="",  # IBKR has no ccxt analogue
                    active=True,
                )
                out.append(info)
                self._instrument_info_cache[native] = info
            except Exception as e:
                log.warning("ibkr universe entry failed (%s): %s", entry, e)
        return out

    async def iter_user_data(self) -> AsyncIterator[FillEvent]:
        """Stream fills + order-status updates as `FillEvent`s.

        Wires `execDetailsEvent` (post-fill) and `orderStatusEvent` (state
        transitions) into an asyncio.Queue and yields each translated event.
        Runs forever; callers cancel by awaiting close().
        """
        await self._ensure_connected()
        queue: asyncio.Queue[FillEvent] = asyncio.Queue(maxsize=2048)

        # Maintain a per-orderId snapshot of (avg_price, filled_qty) so the
        # status-only events can carry the same numbers fills emit.
        order_state: dict[int, tuple[float, float]] = {}

        def _on_exec(trade, fill) -> None:
            try:
                avg = float(getattr(fill.execution, "avgPrice", 0.0) or 0.0)
                # fill.execution.shares is per-fill qty; trade.filled() is cumulative.
                cum = float(getattr(trade.orderStatus, "filled", 0.0) or 0.0)
                order_state[int(trade.order.orderId)] = (avg, cum)
                pnl = float(getattr(fill.commissionReport, "realizedPNL", 0.0) or 0.0)
                ts = getattr(fill.execution, "time", None)
                ts_ms = (
                    int(ts.timestamp() * 1000)
                    if isinstance(ts, datetime)
                    else int(datetime.now(timezone.utc).timestamp() * 1000)
                )
                ev = FillEvent(
                    exchange="ibkr",
                    symbol=self._encode_back(trade.contract),
                    exchange_order_id=str(trade.order.orderId),
                    status=_map_order_status(trade.orderStatus.status),
                    side="buy" if str(trade.order.action).upper() == "BUY" else "sell",
                    filled_qty=cum,
                    avg_price=avg,
                    realized_pnl=pnl,
                    timestamp_ms=ts_ms,
                )
                queue.put_nowait(ev)
            except Exception as e:
                log.warning("ibkr on_exec error: %s", e)

        def _on_status(trade) -> None:
            try:
                avg, cum = order_state.get(int(trade.order.orderId), (0.0, 0.0))
                ev = FillEvent(
                    exchange="ibkr",
                    symbol=self._encode_back(trade.contract),
                    exchange_order_id=str(trade.order.orderId),
                    status=_map_order_status(trade.orderStatus.status),
                    side="buy" if str(trade.order.action).upper() == "BUY" else "sell",
                    filled_qty=cum,
                    avg_price=avg,
                    realized_pnl=0.0,
                    timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
                )
                queue.put_nowait(ev)
            except Exception as e:
                log.warning("ibkr on_status error: %s", e)

        self.ib.execDetailsEvent += _on_exec
        self.ib.orderStatusEvent += _on_status
        try:
            while True:
                yield await queue.get()
        finally:
            try:
                self.ib.execDetailsEvent -= _on_exec
                self.ib.orderStatusEvent -= _on_status
            except Exception:
                pass

    async def iter_klines(
        self, subs: list[tuple[str, str]]
    ) -> AsyncIterator[KlineMsg]:
        """Poll the most recent closed bar per (symbol, tf) at each bar boundary.

        We don't use IBKR's keepUpToDate streaming because (a) it only supports
        5-second bars natively and (b) aggregating into the project's tfs
        (1m..1d) on the client adds drift. Polling once per bar-close is
        simple, drift-free, and within IBKR's request quotas for typical
        watchlist sizes.
        """
        await self._ensure_connected()
        queue: asyncio.Queue[KlineMsg] = asyncio.Queue(maxsize=2048)

        async def _poll(symbol: str, tf: str) -> None:
            tf_s = _TF_SECONDS[tf]
            last_open: int | None = None
            while True:
                # Sleep until ~5 seconds after the next bar boundary so IBKR's
                # historical record has settled.
                now = datetime.now(timezone.utc).timestamp()
                next_boundary = (int(now // tf_s) + 1) * tf_s + 5
                await asyncio.sleep(max(1.0, next_boundary - now))
                try:
                    bars = await self.fetch_klines(symbol, tf, limit=2)
                except Exception as e:
                    log.warning("ibkr poll fetch_klines failed %s %s: %s", symbol, tf, e)
                    continue
                if not bars:
                    continue
                # Emit only NEW closed bars.
                for b in bars:
                    ot = int(b["open_time"])
                    if last_open is not None and ot <= last_open:
                        continue
                    msg = KlineMsg(
                        exchange="ibkr",
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
                    queue.put_nowait(msg)
                    last_open = ot

        tasks = [asyncio.create_task(_poll(s, t)) for s, t in subs]
        try:
            while True:
                yield await queue.get()
        finally:
            for t in tasks:
                t.cancel()

    async def is_market_open(self, symbol: str) -> bool:
        """Return True if the contract is currently within tradingHours.

        Parses the `tradingHours` string from reqContractDetails — format is
        `YYYYMMDD:HHMM-YYYYMMDD:HHMM;...` with `CLOSED` markers for off-days.
        Returns True conservatively if hours can't be parsed (rather than
        blocking trades on a parser bug).
        """
        try:
            await self._ensure_connected()
            contract = await self._resolve_contract(symbol)
            details_list = await self.ib.reqContractDetailsAsync(contract)
            if not details_list:
                return True
            details = details_list[0]
            hours = str(getattr(details, "tradingHours", "") or "")
            tz_name = str(getattr(details, "timeZoneId", "") or "America/New_York")
            return _is_within_trading_hours(hours, tz_name)
        except Exception as e:
            log.warning("ibkr is_market_open failed for %s: %s", symbol, e)
            return True

    async def close(self) -> None:
        if self._connected:
            try:
                self.ib.disconnect()
            except Exception as e:
                log.warning("ibkr disconnect error: %s", e)
            finally:
                self._connected = False
