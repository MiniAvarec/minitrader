from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import current_user
from app.config import get_settings
from app.data.redis_io import get_klines, make_redis
from app.db.models import User

router = APIRouter(prefix="/klines", tags=["klines"])


@router.get("/{symbol}/{tf}")
async def klines(
    symbol: str,
    tf: str,
    limit: int = 200,
    user: User = Depends(current_user),
):
    s = get_settings()
    sym = symbol.upper()
    if sym not in s.symbols:
        raise HTTPException(404, "symbol not tracked")
    if tf not in s.timeframes:
        raise HTTPException(404, "timeframe not tracked")
    r = make_redis()
    try:
        rows = await get_klines(r, sym, tf, limit=min(limit, 500))
        return {"symbol": sym, "tf": tf, "klines": rows}
    finally:
        await r.aclose()
