"""Broker interface used by all multi-exchange code paths.

DB stores exchange-native symbols (`BTCUSDT`, `BTC-USDT-SWAP`, `BTCUSDT` for Bybit linear).
Helpers `to_ccxt_symbol` / `from_ccxt_symbol` convert to/from ccxt's unified form on the wire.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Literal, Optional


ExchangeId = Literal["binance", "okx", "bybit", "ibkr", "exness"]


@dataclass(slots=True)
class InstrumentInfo:
    exchange: str
    symbol: str            # exchange-native, e.g. "BTCUSDT" / "BTC-USDT-SWAP"
    base: str
    quote: str
    contract_type: str     # "usdt-perp" | "spot" | "inverse"
    tick_size: float
    lot_size: float        # qty step
    min_qty: float
    min_notional: float
    ccxt_symbol: str       # "BTC/USDT:USDT"
    active: bool = True
    # Units of `base` per 1.0 of `lot_size`. Crypto venues quote size directly
    # in base units (contract_size == 1.0). MT5/Exness trades in *lots* where a
    # standard FX lot is 100_000 units, metals/CFDs vary — the Exness broker
    # uses this to convert the executor's base-unit qty to MT5 lots.
    contract_size: float = 1.0


@dataclass(slots=True)
class FillEvent:
    exchange: str
    symbol: str                  # exchange-native
    exchange_order_id: str
    status: str                  # "filled" | "partially_filled" | "canceled" | "new" | "rejected"
    side: str                    # "buy" | "sell"
    filled_qty: float
    avg_price: float
    realized_pnl: float
    timestamp_ms: int


@dataclass(slots=True)
class KlineMsg:
    exchange: str
    symbol: str
    tf: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool


class _RolloverState:
    """Per-(symbol, tf) cursor for turning ccxt.pro's repeated in-progress bar
    into exactly one settled (`closed=True`) bar at each rollover."""

    __slots__ = ("last_open", "snap")

    def __init__(self) -> None:
        self.last_open: int | None = None
        self.snap: tuple[float, float, float, float, float] | None = None


def ohlcv_to_klines(
    state: _RolloverState,
    *,
    exchange: str,
    symbol: str,
    tf: str,
    bar: list,
    tf_ms: int,
) -> list[KlineMsg]:
    """Map one ccxt.pro `watch_ohlcv` row to KlineMsgs.

    ccxt.pro re-emits the in-progress candle every tick and never flags the
    moment it settles. We track the last open_time per stream: when a strictly
    newer open_time arrives, the previous candle is finalized — emit it once
    with `closed=True` (using its last seen OHLCV), then the new in-progress
    candle with `closed=False`. Without this no `kline_closed` is ever
    published and the signals worker never evaluates.
    """
    ot = int(bar[0])
    o, h, l, c, v = (
        float(bar[1]),
        float(bar[2]),
        float(bar[3]),
        float(bar[4]),
        float(bar[5]),
    )
    out: list[KlineMsg] = []
    if state.last_open is not None and ot > state.last_open and state.snap:
        po, ph, pl, pc, pv = state.snap
        out.append(
            KlineMsg(
                exchange=exchange,
                symbol=symbol,
                tf=tf,
                open_time=state.last_open,
                close_time=state.last_open + tf_ms - 1,
                open=po,
                high=ph,
                low=pl,
                close=pc,
                volume=pv,
                closed=True,
            )
        )
    out.append(
        KlineMsg(
            exchange=exchange,
            symbol=symbol,
            tf=tf,
            open_time=ot,
            close_time=ot + tf_ms - 1,
            open=o,
            high=h,
            low=l,
            close=c,
            volume=v,
            closed=False,
        )
    )
    if state.last_open is None or ot >= state.last_open:
        state.last_open = ot
        state.snap = (o, h, l, c, v)
    return out


class Broker(ABC):
    """Abstract broker. Concrete subclasses set `exchange_id` and implement every method."""

    exchange_id: ExchangeId = "binance"

    @abstractmethod
    async def usdt_balance(self) -> float: ...

    @abstractmethod
    async def positions(self) -> list[dict]: ...

    @abstractmethod
    async def mark_price(self, symbol: str) -> float: ...

    @abstractmethod
    async def order_book(self, symbol: str, *, limit: int = 20) -> dict: ...

    @abstractmethod
    async def place_market(
        self,
        symbol: str,
        side: str,
        qty: float,
        *,
        sl: float | None = None,
        tp: float | None = None,
        reduce_only: bool = False,
    ) -> dict: ...

    @abstractmethod
    async def fetch_realized_pnl(self, symbol: str, since_ms: int) -> float: ...

    @abstractmethod
    async def fetch_klines(
        self, symbol: str, tf: str, *, end_ms: int | None = None, limit: int = 500
    ) -> list[dict]: ...

    @abstractmethod
    async def load_exchange_info(self) -> list[InstrumentInfo]: ...

    @abstractmethod
    def iter_user_data(self) -> AsyncIterator[FillEvent]: ...

    @abstractmethod
    def iter_klines(self, subs: list[tuple[str, str]]) -> AsyncIterator[KlineMsg]: ...

    @abstractmethod
    async def close(self) -> None: ...


# ----- symbol normalization -----

def to_ccxt_symbol(exchange: str, native: str) -> str:
    """Convert exchange-native symbol to ccxt unified form (futures/swap USDT-margined)."""
    if exchange == "ibkr":
        # IBKR has no ccxt analogue; symbols are dot-encoded (e.g. AAPL.SMART.USD).
        return native
    if exchange == "exness":
        # Exness/MT5 symbols (EURUSD, XAUUSD, BTCUSD, sometimes suffixed like
        # EURUSDm) have no ccxt analogue; pass through unchanged.
        return native
    if exchange == "binance":
        # "BTCUSDT" -> "BTC/USDT:USDT"
        if native.endswith("USDT"):
            return f"{native[:-4]}/USDT:USDT"
        return native
    if exchange == "okx":
        # "BTC-USDT-SWAP" -> "BTC/USDT:USDT"
        if native.endswith("-SWAP"):
            base, quote, _ = native.split("-")
            return f"{base}/{quote}:{quote}"
        return native
    if exchange == "bybit":
        # Bybit linear: native already "BTCUSDT" -> "BTC/USDT:USDT"
        if native.endswith("USDT"):
            return f"{native[:-4]}/USDT:USDT"
        return native
    return native


def from_ccxt_symbol(exchange: str, ccxt_sym: str) -> str:
    """Inverse of to_ccxt_symbol. Best-effort; relies on the `:QUOTE` suffix for swaps."""
    if exchange in ("ibkr", "exness"):
        return ccxt_sym
    if "/" not in ccxt_sym:
        return ccxt_sym
    base_quote, *rest = ccxt_sym.split(":")
    base, quote = base_quote.split("/")
    if exchange == "okx":
        return f"{base}-{quote}-SWAP"
    return f"{base}{quote}"


# ----- IBKR symbol encoding -----
#
# IBKR contracts need (root, routing-exchange, currency) at minimum, plus
# expiry / strike / right for derivatives. We pack everything into a single
# dot-delimited string so it fits the existing String(32) symbol column and
# travels through the signal/order plumbing unchanged.
#
#   STK:  AAPL.SMART.USD
#   FUT:  ES.CME.USD.202509
#   CASH: EUR.IDEALPRO.USD            (Forex pair-base; quote inferred from currency)
#   OPT:  AAPL.SMART.USD.20250620.C.180
#
# `decode_ibkr_symbol` returns a dict the IBKR broker layer feeds to
# ib_insync's Contract factories. Keep this module free of ib_insync imports
# so the rest of the codebase doesn't pull in the dependency.

_IBKR_CONTRACT_TYPES = {"stock", "future", "forex", "option"}


def encode_ibkr_symbol(
    *,
    root: str,
    routing_exchange: str,
    currency: str,
    contract_type: str,
    expiry: str = "",
    right: str = "",
    strike: float = 0.0,
) -> str:
    if contract_type not in _IBKR_CONTRACT_TYPES:
        raise ValueError(f"unknown IBKR contract_type: {contract_type}")
    root = root.upper()
    routing_exchange = routing_exchange.upper()
    currency = currency.upper()
    base = f"{root}.{routing_exchange}.{currency}"
    if contract_type == "stock" or contract_type == "forex":
        return base
    if contract_type == "future":
        if not expiry:
            raise ValueError("future requires expiry (YYYYMM or YYYYMMDD)")
        return f"{base}.{expiry}"
    # option
    if not (expiry and right and strike):
        raise ValueError("option requires expiry, right (C|P) and strike")
    right = right.upper()
    if right not in ("C", "P"):
        raise ValueError("option right must be 'C' or 'P'")
    return f"{base}.{expiry}.{right}.{strike:g}"


def decode_ibkr_symbol(s: str) -> dict:
    parts = s.split(".")
    if len(parts) < 3:
        raise ValueError(f"invalid IBKR symbol: {s!r}")
    root, routing_exchange, currency = parts[0], parts[1], parts[2]
    out: dict = {
        "root": root,
        "routing_exchange": routing_exchange,
        "currency": currency,
    }
    if len(parts) == 3:
        # Stock or forex. Caller decides which based on Instrument.contract_type.
        out["contract_type"] = None  # ambiguous; resolved via Instrument row
        return out
    if len(parts) == 4:
        out["contract_type"] = "future"
        out["expiry"] = parts[3]
        return out
    if len(parts) == 6:
        out["contract_type"] = "option"
        out["expiry"] = parts[3]
        out["right"] = parts[4]
        out["strike"] = float(parts[5])
        return out
    raise ValueError(f"invalid IBKR symbol: {s!r}")
