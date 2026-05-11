from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.db.models import Signal, Strategy, User
from app.db.session import get_db

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
async def list_signals(
    limit: int = 50,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Signal, Strategy.name)
            .outerjoin(Strategy, Strategy.id == Signal.strategy_id)
            # Show: this user's signals; plus any legacy global signals (user_id NULL)
            .where(or_(Signal.user_id == user.id, Signal.user_id.is_(None)))
            .order_by(Signal.created_at.desc())
            .limit(min(limit, 200))
        )
    ).all()
    return [
        {
            "id": r.id,
            "exchange": r.exchange,
            "symbol": r.symbol,
            "side": r.side.value,
            "confidence": r.confidence,
            "entry": r.entry,
            "sl": r.sl,
            "tp": r.tp,
            "status": r.status.value,
            "strategy_id": r.strategy_id,
            "strategy_name": strategy_name,
            "breakdown": r.breakdown,
            "news_refs": r.news_refs,
            "created_at": r.created_at.isoformat(),
        }
        for r, strategy_name in rows
    ]
