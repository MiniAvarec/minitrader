"""Admin-only endpoints: list users, approve pending signups, reject users."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


async def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


class UserRow(BaseModel):
    id: int
    email: str
    is_admin: bool
    is_approved: bool
    created_at: str


def _row(u: User) -> UserRow:
    return UserRow(
        id=u.id,
        email=u.email,
        is_admin=u.is_admin,
        is_approved=u.is_approved,
        created_at=u.created_at.isoformat(),
    )


@router.get("/users", response_model=list[UserRow])
async def list_users(
    _: User = Depends(current_admin), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.execute(select(User).order_by(User.is_approved, User.created_at.desc()))
    ).scalars().all()
    return [_row(u) for u in rows]


@router.post("/users/{user_id}/approve", response_model=UserRow)
async def approve_user(
    user_id: int,
    _: User = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
):
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "user not found")
    if not u.is_approved:
        u.is_approved = True
        await db.commit()
        await db.refresh(u)
    return _row(u)


@router.post("/users/{user_id}/reject")
async def reject_user(
    user_id: int,
    admin: User = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
):
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "user not found")
    if u.is_admin:
        raise HTTPException(400, "cannot reject an admin user")
    if u.id == admin.id:
        raise HTTPException(400, "cannot reject yourself")
    await db.delete(u)
    await db.commit()
    return {"ok": True}
