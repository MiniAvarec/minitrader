"""Symbol canonicalization shared across API routes.

Crypto venues (Binance/OKX/Bybit) use all-uppercase symbols, so the codebase
historically did `symbol.upper()`. Exness/MT5 symbols carry a lowercase
per-account suffix (e.g. `BTCUSDm`), which `.upper()` corrupts. Resolve the
caller-supplied symbol to the instrument's canonical stored casing instead;
fall back to `.upper()` when there's no instrument row so crypto behaviour
(and any pre-instrument edge cases) is unchanged.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Instrument


async def canonical_symbol(db: AsyncSession, exchange: str, symbol: str) -> str:
    row = (
        await db.execute(
            select(Instrument.symbol)
            .where(
                Instrument.exchange == exchange,
                func.upper(Instrument.symbol) == symbol.upper(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row or symbol.upper()
