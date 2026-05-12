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
    passphrase: str | None = None,
    connection_config: str | None = None,
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
    enc_pass = encrypt(passphrase) if passphrase else None
    if existing:
        existing.encrypted_key = enc_key
        existing.encrypted_secret = enc_secret
        existing.encrypted_passphrase = enc_pass
        existing.testnet = testnet
        existing.connection_config = connection_config
        await db.commit()
        await db.refresh(existing)
        return existing
    row = ApiKey(
        user_id=user_id,
        exchange=exchange,
        label=label,
        encrypted_key=enc_key,
        encrypted_secret=enc_secret,
        encrypted_passphrase=enc_pass,
        testnet=testnet,
        connection_config=connection_config,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def load_key(
    db: AsyncSession, user_id: int, exchange: str, label: str = "default"
) -> tuple[str, str, bool, str | None, str | None] | None:
    """Return (api_key, api_secret, testnet, passphrase | None, connection_config | None) or None."""
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
    passphrase = (
        decrypt(row.encrypted_passphrase) if row.encrypted_passphrase else None
    )
    return (
        decrypt(row.encrypted_key),
        decrypt(row.encrypted_secret),
        row.testnet,
        passphrase,
        row.connection_config,
    )


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


async def list_keyed_exchanges(db: AsyncSession, user_id: int) -> list[str]:
    """Return the distinct exchanges this user has a default-label key for."""
    rows = (
        await db.execute(
            select(ApiKey.exchange).where(
                ApiKey.user_id == user_id, ApiKey.label == "default"
            )
        )
    ).all()
    return sorted({r[0] for r in rows})
