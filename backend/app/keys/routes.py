from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.db.models import User
from app.db.session import get_db
from app.keys.store import delete_key, load_key, upsert_key
from app.brokers.binance import BinanceBroker

router = APIRouter(prefix="/keys", tags=["keys"])


class KeyIn(BaseModel):
    exchange: str = "binance"
    api_key: str
    api_secret: str
    testnet: bool = True
    label: str = "default"


class KeyStatus(BaseModel):
    exchange: str
    label: str
    has_key: bool
    testnet: bool | None = None


@router.put("", response_model=KeyStatus)
async def put_key(
    body: KeyIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.exchange != "binance":
        raise HTTPException(400, "only binance supported in v1")
    row = await upsert_key(
        db,
        user.id,
        body.exchange,
        body.api_key,
        body.api_secret,
        label=body.label,
        testnet=body.testnet,
    )
    return KeyStatus(exchange=row.exchange, label=row.label, has_key=True, testnet=row.testnet)


@router.get("", response_model=list[KeyStatus])
async def list_keys(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    out: list[KeyStatus] = []
    for ex in ["binance"]:
        loaded = await load_key(db, user.id, ex)
        if loaded is None:
            out.append(KeyStatus(exchange=ex, label="default", has_key=False))
        else:
            _, _, testnet = loaded
            out.append(KeyStatus(exchange=ex, label="default", has_key=True, testnet=testnet))
    return out


@router.delete("/{exchange}")
async def del_key(
    exchange: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_key(db, user.id, exchange)
    return {"ok": ok}


@router.post("/test")
async def test_key(
    body: KeyIn,
    user: User = Depends(current_user),
):
    if body.exchange != "binance":
        raise HTTPException(400, "only binance supported in v1")
    broker = BinanceBroker(api_key=body.api_key, api_secret=body.api_secret, testnet=body.testnet)
    try:
        balance = await broker.usdt_balance()
        return {"ok": True, "usdt_balance": balance}
    except Exception as e:
        raise HTTPException(400, f"connection failed: {e}")
    finally:
        await broker.close()
