import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.brokers.factory import SUPPORTED, get_broker, invalidate_user_creds
from app.data.redis_io import make_redis
from app.db.models import User
from app.db.session import get_db
from app.keys.store import delete_key, load_key, upsert_key

router = APIRouter(prefix="/keys", tags=["keys"])


ExchangeLit = Literal["binance", "okx", "bybit"]


class KeyIn(BaseModel):
    exchange: ExchangeLit = "binance"
    api_key: str
    api_secret: str
    passphrase: str | None = None
    testnet: bool = True
    label: str = "default"


class KeyStatus(BaseModel):
    exchange: str
    label: str
    has_key: bool
    testnet: bool | None = None


def _validate(exchange: str, passphrase: str | None) -> None:
    if exchange not in SUPPORTED:
        raise HTTPException(400, f"unsupported exchange: {exchange}")
    if exchange == "okx" and not passphrase:
        raise HTTPException(400, "OKX requires a passphrase")


async def _publish_keys_changed(user_id: int, exchange: str, present: bool) -> None:
    try:
        r = make_redis()
        await r.publish(
            "keys:changed",
            json.dumps({"user_id": user_id, "exchange": exchange, "present": present}),
        )
    except Exception:
        pass


@router.put("", response_model=KeyStatus)
async def put_key(
    body: KeyIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate(body.exchange, body.passphrase)
    row = await upsert_key(
        db,
        user.id,
        body.exchange,
        body.api_key,
        body.api_secret,
        label=body.label,
        testnet=body.testnet,
        passphrase=body.passphrase,
    )
    invalidate_user_creds(user.id, body.exchange)
    await _publish_keys_changed(user.id, body.exchange, present=True)
    return KeyStatus(exchange=row.exchange, label=row.label, has_key=True, testnet=row.testnet)


@router.get("", response_model=list[KeyStatus])
async def list_keys(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    out: list[KeyStatus] = []
    for ex in SUPPORTED:
        loaded = await load_key(db, user.id, ex)
        if loaded is None:
            out.append(KeyStatus(exchange=ex, label="default", has_key=False))
        else:
            _, _, testnet, _ = loaded
            out.append(KeyStatus(exchange=ex, label="default", has_key=True, testnet=testnet))
    return out


@router.delete("/{exchange}")
async def del_key(
    exchange: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_key(db, user.id, exchange)
    if ok:
        invalidate_user_creds(user.id, exchange)
        await _publish_keys_changed(user.id, exchange, present=False)
    return {"ok": ok}


@router.post("/test")
async def test_key(
    body: KeyIn,
    user: User = Depends(current_user),
):
    _validate(body.exchange, body.passphrase)
    broker = get_broker(
        body.exchange,
        body.api_key,
        body.api_secret,
        testnet=body.testnet,
        passphrase=body.passphrase,
    )
    try:
        balance = await broker.usdt_balance()
        return {"ok": True, "usdt_balance": balance}
    except Exception as e:
        raise HTTPException(400, f"connection failed: {e}")
    finally:
        await broker.close()
