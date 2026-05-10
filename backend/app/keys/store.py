from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApiKey
from app.keys.crypto import decrypt, encrypt


async def upsert_key(
    db: AsyncSession,
    user_id: int,
    exchange: str,
    api_key: str,
    api_secret: str,
    *,
    label: str = "default",
    testnet: bool = True,
) -> ApiKey:
    existing = (
        await db.execute(
            select(ApiKey).where(
                ApiKey.user_id == user_id,
                ApiKey.exchange == exchange,
                ApiKey.label == label,
            )
        )
    ).scalar_one_or_none()
    enc_key = encrypt(api_key)
    enc_secret = encrypt(api_secret)
    if existing:
        existing.encrypted_key = enc_key
        existing.encrypted_secret = enc_secret
        existing.testnet = testnet
        await db.commit()
        await db.refresh(existing)
        return existing
    row = ApiKey(
        user_id=user_id,
        exchange=exchange,
        label=label,
        encrypted_key=enc_key,
        encrypted_secret=enc_secret,
        testnet=testnet,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def load_key(
    db: AsyncSession, user_id: int, exchange: str, label: str = "default"
) -> tuple[str, str, bool] | None:
    row = (
        await db.execute(
            select(ApiKey).where(
                ApiKey.user_id == user_id,
                ApiKey.exchange == exchange,
                ApiKey.label == label,
            )
        )
    ).scalar_one_or_none()
    if not row:
        return None
    return decrypt(row.encrypted_key), decrypt(row.encrypted_secret), row.testnet


async def delete_key(
    db: AsyncSession, user_id: int, exchange: str, label: str = "default"
) -> bool:
    row = (
        await db.execute(
            select(ApiKey).where(
                ApiKey.user_id == user_id,
                ApiKey.exchange == exchange,
                ApiKey.label == label,
            )
        )
    ).scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
