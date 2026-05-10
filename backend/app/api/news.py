from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.db.models import NewsItem, User
from app.db.session import get_db

router = APIRouter(prefix="/news", tags=["news"])


@router.get("")
async def list_news(
    hours: int = 6,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min(hours, 48))
    rows = (
        await db.execute(
            select(NewsItem)
            .where(NewsItem.published_at >= cutoff)
            .order_by(NewsItem.published_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return [
        {
            "source": r.source,
            "headline": r.headline,
            "url": r.url,
            "symbols": r.symbols or [],
            "sentiment": r.sentiment,
            "published_at": r.published_at.isoformat(),
        }
        for r in rows
    ]
