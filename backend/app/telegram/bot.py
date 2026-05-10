"""Telegram bot worker.

- Verifies chat binding via /start <token>
- Subscribes to the `signals` Redis channel and pushes signal cards with inline buttons
- Inline buttons hit FastAPI via httpx using a worker shared secret to execute / dismiss
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app.config import get_settings
from app.data.redis_io import SIGNAL_CHANNEL, make_redis, subscribe
from app.db.models import User
from app.db.session import SessionLocal

log = logging.getLogger("telegram")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

API_BASE = "http://backend:8000"


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Welcome! Open the trader web app, copy your link token from Settings, "
            "and run: /start <token>"
        )
        return
    token = args[0]
    chat_id = str(update.effective_chat.id)
    async with SessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.telegram_link_token == token))
        ).scalar_one_or_none()
        if user is None:
            await update.message.reply_text("Invalid or expired token.")
            return
        user.telegram_chat_id = chat_id
        user.telegram_link_token = None
        await db.commit()
    await update.message.reply_text("Bound — you'll receive signals here.")


async def _callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return
    await q.answer()
    data = q.data or ""
    parts = data.split(":", 2)
    if len(parts) < 2:
        return
    action, signal_id = parts[0], parts[1]
    chat_id = str(q.message.chat.id) if q.message else None
    if not chat_id:
        return
    s = get_settings()
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{API_BASE}/internal/telegram-action",
                json={"action": action, "signal_id": int(signal_id), "chat_id": chat_id},
                headers={"X-Worker-Secret": s.WORKER_SHARED_SECRET},
            )
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"detail": resp.text}
        except Exception as e:
            body = {"ok": False, "error": str(e)}
    if body.get("ok"):
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(body.get("message") or "ok")
    else:
        await q.message.reply_text(f"Failed: {body.get('error') or body.get('detail') or 'unknown'}")


def _format(payload: dict) -> str:
    side_emoji = "BUY" if payload.get("side") == "buy" else "SELL"
    sl = payload.get("sl")
    tp = payload.get("tp")
    name = payload.get("strategy_name") or "strategy"
    lines = [
        f"<b>{side_emoji} {payload.get('symbol')}</b>  conf {payload.get('confidence'):.0f}  · <i>{name}</i>",
        f"entry: <code>{payload.get('entry')}</code>",
    ]
    if sl is not None:
        lines.append(f"SL: <code>{sl}</code>")
    if tp is not None:
        lines.append(f"TP: <code>{tp}</code>")
    refs = payload.get("news_refs") or []
    if refs:
        lines.append("news:")
        for r in refs[:3]:
            lines.append(f"  • {r.get('headline')}")
    return "\n".join(lines)


def _keyboard(signal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Execute @ market", callback_data=f"exec:{signal_id}"),
                InlineKeyboardButton("Dismiss", callback_data=f"dismiss:{signal_id}"),
            ]
        ]
    )


async def _signals_loop(app: Application) -> None:
    r = make_redis()
    pubsub = await subscribe(r, [SIGNAL_CHANNEL])
    log.info("telegram listening for signals")
    async for msg in pubsub.listen():
        if msg.get("type") != "message":
            continue
        try:
            payload = json.loads(msg["data"])
        except Exception:
            continue
        if payload.get("event") != "signal":
            continue
        user_id = payload.get("user_id")
        if user_id is None:
            continue
        async with SessionLocal() as db:
            user = (
                await db.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
        if not user or not user.telegram_chat_id:
            continue
        try:
            await app.bot.send_message(
                chat_id=int(user.telegram_chat_id),
                text=_format(payload),
                parse_mode=ParseMode.HTML,
                reply_markup=_keyboard(int(payload["id"])),
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning("send to %s failed: %s", user.telegram_chat_id, e)


async def main() -> None:
    s = get_settings()
    if not s.TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set; telegram worker idle")
        while True:
            await asyncio.sleep(3600)
    app = Application.builder().token(s.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CallbackQueryHandler(_callback))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    try:
        await _signals_loop(app)
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
