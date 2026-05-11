from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.auth.jwt import EXPIRE_HOURS, issue_token
from app.auth.password import hash_password, verify_password
from app.config import get_settings
from app.db.models import RiskConfig, User
from app.db.session import get_db
from app.security import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str


class Me(BaseModel):
    id: int
    email: str
    mode: str
    telegram_chat_id: str | None
    is_admin: bool


def _set_session(resp: Response, user_id: int) -> None:
    token = issue_token(user_id)
    resp.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="lax",
        # Cloud provider terminates TLS and forwards the request; cookies must
        # only be sent over HTTPS. In dev (no TLS) keep secure off so the
        # cookie still flows over http://localhost.
        secure=get_settings().APP_ENV != "dev",
        max_age=60 * 60 * EXPIRE_HOURS,
    )


def _me(user: User) -> Me:
    return Me(
        id=user.id,
        email=user.email,
        mode=user.mode.value,
        telegram_chat_id=user.telegram_chat_id,
        is_admin=user.is_admin,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def register(
    request: Request,
    creds: Credentials,
    resp: Response,
    db: AsyncSession = Depends(get_db),
):
    existing = (
        await db.execute(select(User).where(User.email == creds.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    admin_email = (get_settings().ADMIN_EMAIL or "").strip().lower()
    is_admin_signup = bool(admin_email) and creds.email.lower() == admin_email

    if is_admin_signup:
        # Only the very first registration with the admin email is auto-promoted.
        # If an admin already exists, fall back to the normal pending flow so a
        # leaked/guessed admin email can't be claimed twice.
        admin_exists = (
            await db.execute(select(func.count(User.id)).where(User.is_admin.is_(True)))
        ).scalar_one()
        if admin_exists:
            is_admin_signup = False

    user = User(
        email=creds.email,
        password_hash=hash_password(creds.password),
        is_admin=is_admin_signup,
        is_approved=is_admin_signup,
    )
    db.add(user)
    await db.flush()
    db.add(RiskConfig(user_id=user.id))
    await db.commit()
    await db.refresh(user)

    if user.is_approved:
        _set_session(resp, user.id)
        return {"status": "approved", **_me(user).model_dump()}
    return {
        "status": "pending",
        "message": "Account created — awaiting admin approval.",
    }


@router.post("/login", response_model=Me)
@limiter.limit("10/minute")
async def login(
    request: Request,
    creds: Credentials,
    resp: Response,
    db: AsyncSession = Depends(get_db),
):
    user = (
        await db.execute(select(User).where(User.email == creds.email))
    ).scalar_one_or_none()
    if not user or not verify_password(creds.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not user.is_approved:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "account pending admin approval"
        )
    _set_session(resp, user.id)
    return _me(user)


@router.post("/logout")
async def logout(resp: Response):
    resp.delete_cookie("session")
    return {"ok": True}


@router.get("/me", response_model=Me)
async def me(user: User = Depends(current_user)):
    return _me(user)


@router.get("/ws-token")
async def ws_token(user: User = Depends(current_user)):
    """Returns a short-lived JWT the frontend uses as ?token= for the WS upgrade."""
    # 5 minutes is plenty — the frontend fetches a new token right before
    # opening the socket. Short lifetime limits exposure if a URL with the
    # token leaks via logs or proxies.
    return {"token": issue_token(user.id, expires_in_hours=5 / 60)}
