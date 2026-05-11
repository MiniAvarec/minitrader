"""System-wide integration settings (third-party API keys etc.).

Stored encrypted in the `app_settings` table using the same Fernet key as
user exchange credentials. Reads fall back to the corresponding environment
variable in `Settings` so existing deployments keep working without a write.

The fetchers (Finnhub, CryptoPanic, …) call `get_setting()` on every poll;
that's a cheap indexed primary-key lookup over a tiny table and lets users
change a key without restarting the news worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import select

from app.config import get_settings
from app.db.models import AppSetting
from app.db.session import SessionLocal
from app.keys.crypto import decrypt, encrypt


@dataclass(frozen=True)
class IntegrationDef:
    """Metadata for one configurable integration."""
    slug: str           # stable id used in URLs and DB rows
    label: str          # human label for the UI
    env_var: str | None  # fallback env var name, if any
    secret: bool        # True => mask in API responses; False => return as-is
    description: str    # one-liner for the UI


# Single source of truth used by the API, the UI, and the fetchers.
INTEGRATIONS: tuple[IntegrationDef, ...] = (
    IntegrationDef(
        slug="finnhub_api_key",
        label="Finnhub",
        env_var="FINNHUB_API_KEY",
        secret=True,
        description="Crypto news headlines + per-article ids.",
    ),
    IntegrationDef(
        slug="cryptopanic_api_key",
        label="CryptoPanic",
        env_var="CRYPTOPANIC_API_KEY",
        secret=True,
        description="Community-voted crypto news with sentiment.",
    ),
    IntegrationDef(
        slug="cryptocompare_api_key",
        label="CryptoCompare",
        env_var="CRYPTOCOMPARE_API_KEY",
        secret=True,
        description="150+ source crypto news aggregator (free with key).",
    ),
    IntegrationDef(
        slug="newsdata_api_key",
        label="NewsData.io",
        env_var="NEWSDATA_API_KEY",
        secret=True,
        description="Mainstream business news mentioning crypto (free 200/day).",
    ),
    IntegrationDef(
        slug="reddit_user_agent",
        label="Reddit User-Agent",
        env_var="REDDIT_USER_AGENT",
        secret=False,
        description='Required UA for Reddit\'s public JSON. Example: "minitrader/0.1 (by /u/you)".',
    ),
)

_BY_SLUG: dict[str, IntegrationDef] = {i.slug: i for i in INTEGRATIONS}


def integration(slug: str) -> IntegrationDef:
    if slug not in _BY_SLUG:
        raise KeyError(f"unknown integration {slug!r}")
    return _BY_SLUG[slug]


def _env_fallback(slug: str) -> str:
    spec = _BY_SLUG.get(slug)
    if spec is None or spec.env_var is None:
        return ""
    return getattr(get_settings(), spec.env_var, "") or ""


async def get_setting(slug: str) -> str:
    """Return the current value (DB first, env fallback). Empty string if unset."""
    if slug not in _BY_SLUG:
        return ""
    async with SessionLocal() as db:
        row = (
            await db.execute(select(AppSetting).where(AppSetting.key == slug))
        ).scalar_one_or_none()
    if row is None:
        return _env_fallback(slug)
    try:
        return decrypt(row.encrypted_value)
    except Exception:
        return _env_fallback(slug)


async def set_setting(slug: str, value: str) -> None:
    """Upsert an encrypted value. Empty value is treated as 'delete'."""
    if slug not in _BY_SLUG:
        raise KeyError(slug)
    if not value:
        await delete_setting(slug)
        return
    enc = encrypt(value)
    async with SessionLocal() as db:
        existing = (
            await db.execute(select(AppSetting).where(AppSetting.key == slug))
        ).scalar_one_or_none()
        if existing is None:
            db.add(AppSetting(key=slug, encrypted_value=enc))
        else:
            existing.encrypted_value = enc
        await db.commit()


async def delete_setting(slug: str) -> bool:
    if slug not in _BY_SLUG:
        return False
    async with SessionLocal() as db:
        existing = (
            await db.execute(select(AppSetting).where(AppSetting.key == slug))
        ).scalar_one_or_none()
        if existing is None:
            return False
        await db.delete(existing)
        await db.commit()
        return True


async def status(slug: str) -> dict:
    """Return UI-friendly status (no plaintext for secrets)."""
    spec = integration(slug)
    async with SessionLocal() as db:
        row = (
            await db.execute(select(AppSetting).where(AppSetting.key == slug))
        ).scalar_one_or_none()
    in_db = row is not None
    in_env = bool(_env_fallback(slug))
    out: dict = {
        "slug": spec.slug,
        "label": spec.label,
        "description": spec.description,
        "secret": spec.secret,
        "in_db": in_db,
        "in_env": in_env,
        "updated_at": row.updated_at.isoformat() if row else None,
    }
    if not spec.secret:
        # Non-secret values are returned plaintext so users can see/edit them.
        if in_db:
            try:
                out["value"] = decrypt(row.encrypted_value)
            except Exception:
                out["value"] = ""
        else:
            out["value"] = _env_fallback(slug)
    return out
