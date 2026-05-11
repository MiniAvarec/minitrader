from datetime import datetime, timedelta, timezone
import jwt

from app.config import get_settings

ALGO = "HS256"
EXPIRE_HOURS = 24  # session cookie + JWT lifetime


def issue_token(user_id: int, expires_in_hours: float = EXPIRE_HOURS) -> str:
    s = get_settings()
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, s.JWT_SECRET, algorithm=ALGO)


def decode_token(token: str) -> int:
    s = get_settings()
    payload = jwt.decode(token, s.JWT_SECRET, algorithms=[ALGO])
    return int(payload["sub"])
