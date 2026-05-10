"""Internal endpoints called by worker processes (e.g. Telegram bot callbacks).

Authenticated by the WORKER_SHARED_SECRET header — these endpoints must not be
reachable from the public internet.
"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Signal as SignalModel, SignalStatus, User
from app.db.session import SessionLocal
from app.orders.executor import place_for_signal

router = APIRouter(prefix="/internal", tags=["internal"])


class TelegramAction(BaseModel):
    action: str  # "exec" | "dismiss"
    signal_id: int
    chat_id: str


@router.post("/telegram-action")
async def telegram_action(
    body: TelegramAction,
    x_worker_secret: str | None = Header(default=None),
):
    if x_worker_secret != get_settings().WORKER_SHARED_SECRET:
        raise HTTPException(401, "bad worker secret")
    async with SessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.telegram_chat_id == body.chat_id))
        ).scalar_one_or_none()
        if user is None:
            return {"ok": False, "error": "chat not bound to any user"}
        sig = (
            await db.execute(select(SignalModel).where(SignalModel.id == body.signal_id))
        ).scalar_one_or_none()
        if sig is None:
            return {"ok": False, "error": "signal not found"}
        if body.action == "dismiss":
            sig.status = SignalStatus.dismissed
            await db.commit()
            return {"ok": True, "message": "dismissed"}
        if body.action == "exec":
            ok, reason, order = await place_for_signal(db=db, user=user, signal=sig)
            if ok:
                sig.status = SignalStatus.executed
                await db.commit()
                return {"ok": True, "message": f"executed: order {order.exchange_order_id}"}
            return {"ok": False, "error": reason}
    return {"ok": False, "error": "unknown action"}
