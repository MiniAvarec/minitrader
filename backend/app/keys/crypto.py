from functools import lru_cache
from cryptography.fernet import Fernet

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().MASTER_KEY.encode()
    return Fernet(key)


def encrypt(plain: str) -> bytes:
    return _fernet().encrypt(plain.encode())


def decrypt(token: bytes) -> str:
    return _fernet().decrypt(token).decode()
