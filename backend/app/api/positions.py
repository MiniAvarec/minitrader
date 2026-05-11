from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.brokers.factory import get_broker_for_user
from app.db.models import User
from app.db.session import get_db
from app.keys.store import list_keyed_exchanges

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("")
async def list_positions(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    """Return balance + open positions across every exchange the user has keys for."""
    exchanges = await list_keyed_exchanges(db, user.id)
    out: list[dict] = []
    for exchange in exchanges:
        broker = await get_broker_for_user(db, user.id, exchange)
        if broker is None:
            continue
        try:
            positions = await broker.positions()
            balance = await broker.usdt_balance()
            out.append(
                {"exchange": exchange, "usdt_balance": balance, "positions": positions}
            )
        finally:
            await broker.close()
    return {"exchanges": out}
