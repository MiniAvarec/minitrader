from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.brokers.factory import SUPPORTED
from app.config import get_settings
from app.db.models import Instrument, User
from app.db.session import get_db
from app.keys.store import list_keyed_exchanges

router = APIRouter(prefix="/exchanges", tags=["exchanges"])


@router.get("")
async def list_exchanges(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    """List exchanges this deployment supports, with the user's key status."""
    s = get_settings()
    keyed = set(await list_keyed_exchanges(db, user.id))
    out = []
    for ex in SUPPORTED:
        if ex not in s.enabled_exchanges:
            continue
        out.append({
            "id": ex,
            "label": ex.upper(),
            "has_key": ex in keyed,
            "testnet": s.testnet_for(ex),
        })
    return out


@router.get("/{exchange}/instruments")
async def list_instruments(
    exchange: str,
    search: str = "",
    limit: int = 50,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search the cached exchangeInfo. Use this to populate the Add-Pair dialog."""
    if exchange not in SUPPORTED:
        raise HTTPException(404, "unknown exchange")
    if limit < 1 or limit > 500:
        limit = 50
    q = select(Instrument).where(Instrument.exchange == exchange, Instrument.active.is_(True))
    if search:
        like = f"%{search.upper()}%"
        # Match the native symbol (BTCUSDT / BTC-USDT-SWAP), the base coin (BTC),
        # or the unified BASE+QUOTE concatenation so "BTCUSDT" finds OKX's
        # BTC-USDT-SWAP and Bybit's BTCUSDT alike.
        q = q.where(
            Instrument.symbol.ilike(like)
            | Instrument.base.ilike(like)
            | func.concat(Instrument.base, Instrument.quote).ilike(like)
        )
    q = q.order_by(Instrument.symbol).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "exchange": r.exchange,
            "symbol": r.symbol,
            "base": r.base,
            "quote": r.quote,
            "tick_size": r.tick_size,
            "lot_size": r.lot_size,
            "min_qty": r.min_qty,
            "min_notional": r.min_notional,
            "ccxt_symbol": r.ccxt_symbol,
        }
        for r in rows
    ]
