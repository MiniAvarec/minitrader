import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.brokers.factory import SUPPORTED
from app.data.redis_io import WATCHLIST_CHANGED_CHANNEL, make_redis
from app.db.models import Instrument, User, UserWatchlistEntry
from app.db.session import get_db

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistIn(BaseModel):
    exchange: str
    symbol: str


async def _publish_changed(user_id: int, exchange: str, symbol: str) -> None:
    try:
        r = make_redis()
        await r.publish(
            WATCHLIST_CHANGED_CHANNEL,
            json.dumps({"user_id": user_id, "exchange": exchange, "symbol": symbol}),
        )
    except Exception:
        pass


@router.get("")
async def list_watchlist(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    """Return the user's pairs joined with cached instrument metadata."""
    q = (
        select(UserWatchlistEntry, Instrument)
        .join(
            Instrument,
            (Instrument.exchange == UserWatchlistEntry.exchange)
            & (Instrument.symbol == UserWatchlistEntry.symbol),
        )
        .where(UserWatchlistEntry.user_id == user.id)
        .order_by(UserWatchlistEntry.exchange, UserWatchlistEntry.symbol)
    )
    rows = (await db.execute(q)).all()
    return [
        {
            "exchange": e.exchange,
            "symbol": e.symbol,
            "enabled": e.enabled,
            "base": i.base,
            "quote": i.quote,
            "tick_size": i.tick_size,
            "lot_size": i.lot_size,
            "min_notional": i.min_notional,
            "ccxt_symbol": i.ccxt_symbol,
        }
        for e, i in rows
    ]


@router.post("")
async def add_watchlist(
    body: WatchlistIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.exchange not in SUPPORTED:
        raise HTTPException(400, "unknown exchange")
    instrument = (
        await db.execute(
            select(Instrument).where(
                Instrument.exchange == body.exchange, Instrument.symbol == body.symbol
            )
        )
    ).scalar_one_or_none()
    if instrument is None or not instrument.active:
        raise HTTPException(404, "instrument not found for this exchange")
    existing = (
        await db.execute(
            select(UserWatchlistEntry).where(
                UserWatchlistEntry.user_id == user.id,
                UserWatchlistEntry.exchange == body.exchange,
                UserWatchlistEntry.symbol == body.symbol,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            UserWatchlistEntry(
                user_id=user.id,
                exchange=body.exchange,
                symbol=body.symbol,
                enabled=True,
            )
        )
        await db.commit()
    await _publish_changed(user.id, body.exchange, body.symbol)
    return {"ok": True}


@router.delete("/{exchange}/{symbol}")
async def remove_watchlist(
    exchange: str,
    symbol: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(UserWatchlistEntry).where(
                UserWatchlistEntry.user_id == user.id,
                UserWatchlistEntry.exchange == exchange,
                UserWatchlistEntry.symbol == symbol,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return {"ok": False}
    await db.delete(row)
    await db.commit()
    await _publish_changed(user.id, exchange, symbol)
    return {"ok": True}
