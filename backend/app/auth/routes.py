from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.auth.jwt import issue_token
from app.auth.password import hash_password, verify_password
from app.config import get_settings
from app.db.models import RiskConfig, User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str


class Me(BaseModel):
    id: int
    email: str
    mode: str
    telegram_chat_id: str | None


def _set_session(resp: Response, user_id: int) -> None:
    token = issue_token(user_id)
    resp.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="lax",
        secure=get_settings().APP_ENV != "dev",
        max_age=60 * 60 * 24 * 7,
    )


@router.post("/register", response_model=Me, status_code=status.HTTP_201_CREATED)
async def register(creds: Credentials, resp: Response, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(User).where(User.email == creds.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    user = User(email=creds.email, password_hash=hash_password(creds.password))
    db.add(user)
    await db.flush()
    db.add(RiskConfig(user_id=user.id))
    await db.commit()
    await db.refresh(user)
    _set_session(resp, user.id)
    return Me(id=user.id, email=user.email, mode=user.mode.value, telegram_chat_id=user.telegram_chat_id)


@router.post("/login", response_model=Me)
async def login(creds: Credentials, resp: Response, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == creds.email))).scalar_one_or_none()
    if not user or not verify_password(creds.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    _set_session(resp, user.id)
    return Me(id=user.id, email=user.email, mode=user.mode.value, telegram_chat_id=user.telegram_chat_id)


@router.post("/logout")
async def logout(resp: Response):
    resp.delete_cookie("session")
    return {"ok": True}


@router.get("/me", response_model=Me)
async def me(user: User = Depends(current_user)):
    return Me(
        id=user.id, email=user.email, mode=user.mode.value, telegram_chat_id=user.telegram_chat_id
    )


@router.get("/ws-token")
async def ws_token(user: User = Depends(current_user)):
    """Returns a JWT the frontend can use as ?token= for the WS upgrade."""
    return {"token": issue_token(user.id)}
