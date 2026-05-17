from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.brokers.factory import SUPPORTED
from app.config import get_settings
from app.data.redis_io import get_klines, make_redis
from app.db.models import Instrument, User
from app.db.session import get_db

router = APIRouter(prefix="/klines", tags=["klines"])


@router.get("/{exchange}/{symbol}/{tf}")
async def klines(
    exchange: str,
    symbol: str,
    tf: str,
    limit: int = 200,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if exchange not in SUPPORTED:
        raise HTTPException(404, "unknown exchange")
    s = get_settings()
    if tf not in s.default_timeframes:
        raise HTTPException(404, "timeframe not tracked")
    # Match case-insensitively: crypto venues are all-uppercase but MT5/Exness
    # symbols carry a lowercase account suffix (e.g. BTCUSDm), so don't force
    # .upper(). Use the instrument's canonical stored symbol for the Redis key.
    instrument = (
        await db.execute(
            select(Instrument).where(
                Instrument.exchange == exchange,
                func.upper(Instrument.symbol) == symbol.upper(),
            )
        )
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, "symbol not tracked")
    sym = instrument.symbol
    r = make_redis()
    try:
        rows = await get_klines(r, exchange, sym, tf, limit=min(limit, 500))
        return {"exchange": exchange, "symbol": sym, "tf": tf, "klines": rows}
    finally:
        await r.aclose()
