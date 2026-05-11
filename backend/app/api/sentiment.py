"""Market-sentiment endpoints (Fear & Greed Index, etc.)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.db.models import MarketSentiment, User
from app.db.session import get_db

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


@router.get("/fear-greed")
async def get_fear_greed(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(MarketSentiment)
            .where(MarketSentiment.source == "fear_greed")
            .order_by(MarketSentiment.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="no fear/greed data yet")
    return {
        "value": row.value,
        "classification": row.classification,
        "fetched_at": row.fetched_at.isoformat(),
    }
