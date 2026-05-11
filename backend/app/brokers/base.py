"""Broker interface used by all multi-exchange code paths.

DB stores exchange-native symbols (`BTCUSDT`, `BTC-USDT-SWAP`, `BTCUSDT` for Bybit linear).
Helpers `to_ccxt_symbol` / `from_ccxt_symbol` convert to/from ccxt's unified form on the wire.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Literal, Optional


ExchangeId = Literal["binance", "okx", "bybit"]


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
    if "/" not in ccxt_sym:
        return ccxt_sym
    base_quote, *rest = ccxt_sym.split(":")
    base, quote = base_quote.split("/")
    if exchange == "okx":
        return f"{base}-{quote}-SWAP"
    return f"{base}{quote}"
