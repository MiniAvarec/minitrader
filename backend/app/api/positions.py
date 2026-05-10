from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.brokers.binance import BinanceBroker
from app.db.models import User
from app.db.session import get_db
from app.keys.store import load_key

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("")
async def list_positions(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    loaded = await load_key(db, user.id, "binance")
    if loaded is None:
        raise HTTPException(400, "no Binance API key on file")
    api_key, api_secret, testnet = loaded
    broker = BinanceBroker(api_key, api_secret, testnet=testnet)
    try:
        positions = await broker.positions()
        balance = await broker.usdt_balance()
        return {"usdt_balance": balance, "positions": positions}
    finally:
        await broker.close()
