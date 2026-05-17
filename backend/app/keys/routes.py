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


ExchangeLit = Literal["binance", "okx", "bybit", "ibkr", "exness"]


class IBKRConfig(BaseModel):
    host: str = "ibgateway"
    port: int = 4002
    client_id: int = 4
    account: str | None = None


class ExnessConfig(BaseModel):
    # MT5 server name decides demo vs live (Exness-MT5TrialN / Exness-MT5RealN).
    server: str = ""
    bridge_host: str = "mt5gateway"
    bridge_port: int = 18812


class KeyIn(BaseModel):
    exchange: ExchangeLit = "binance"
    # Crypto exchanges only — empty strings for IBKR/Exness.
    api_key: str = ""
    api_secret: str = ""
    passphrase: str | None = None
    testnet: bool = True
    label: str = "default"
    # IBKR only — host/port/client_id/account. Ignored by other exchanges.
    ibkr: IBKRConfig | None = None
    # Exness only — MT5 server + bridge address. api_key=MT5 login number,
    # api_secret=MT5 password.
    exness: ExnessConfig | None = None


class KeyStatus(BaseModel):
    exchange: str
    label: str
    has_key: bool
    testnet: bool | None = None


def _validate(body: KeyIn) -> None:
    if body.exchange not in SUPPORTED:
        raise HTTPException(400, f"unsupported exchange: {body.exchange}")
    if body.exchange == "okx" and not body.passphrase:
        raise HTTPException(400, "OKX requires a passphrase")
    if body.exchange == "ibkr":
        if body.ibkr is None:
            raise HTTPException(400, "IBKR requires host/port/client_id")
        if not body.ibkr.host or not body.ibkr.port or not body.ibkr.client_id:
            raise HTTPException(400, "IBKR host/port/client_id must be set")
    elif body.exchange == "exness":
        if body.exness is None or not body.exness.server:
            raise HTTPException(400, "Exness requires an MT5 server name")
        if not body.api_key or not body.api_secret:
            raise HTTPException(
                400, "Exness requires MT5 login (api_key) and password (api_secret)"
            )
    else:
        if not body.api_key or not body.api_secret:
            raise HTTPException(400, f"{body.exchange} requires api_key and api_secret")


def _connection_config_json(body: KeyIn) -> str | None:
    if body.exchange == "ibkr" and body.ibkr is not None:
        return json.dumps(
            {
                "host": body.ibkr.host,
                "port": int(body.ibkr.port),
                "client_id": int(body.ibkr.client_id),
                "account": body.ibkr.account or None,
            }
        )
    if body.exchange == "exness" and body.exness is not None:
        return json.dumps(
            {
                "server": body.exness.server,
                "bridge_host": body.exness.bridge_host,
                "bridge_port": int(body.exness.bridge_port),
            }
        )
    return None


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
    _validate(body)
    row = await upsert_key(
        db,
        user.id,
        body.exchange,
        body.api_key,
        body.api_secret,
        label=body.label,
        testnet=body.testnet,
        passphrase=body.passphrase,
        connection_config=_connection_config_json(body),
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
            _, _, testnet, _, _ = loaded
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
    _validate(body)
    broker = get_broker(
        body.exchange,
        body.api_key,
        body.api_secret,
        testnet=body.testnet,
        passphrase=body.passphrase,
        connection_config=_connection_config_json(body),
    )
    try:
        balance = await broker.usdt_balance()
        return {"ok": True, "usdt_balance": balance}
    except Exception as e:
        raise HTTPException(400, f"connection failed: {e}")
    finally:
        await broker.close()
