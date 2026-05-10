"""WebSocket endpoint that fans out signal + news pubsub to the React frontend."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.jwt import decode_token
from app.data.redis_io import NEWS_CHANNEL, SIGNAL_CHANNEL, make_redis, subscribe

log = logging.getLogger("ws")
router = APIRouter()


@router.websocket("/ws/live")
async def live(ws: WebSocket) -> None:
    # Auth via query token (frontend passes ?token=<session-cookie-value>)
    token = ws.query_params.get("token")
    try:
        decode_token(token or "")
    except Exception:
        await ws.close(code=4401)
        return
    await ws.accept()
    r = make_redis()
    pubsub = await subscribe(r, [SIGNAL_CHANNEL, NEWS_CHANNEL])

    async def _pump() -> None:
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                payload = json.loads(msg["data"])
            except Exception:
                continue
            channel = msg.get("channel")
            payload["_channel"] = channel
            try:
                await ws.send_json(payload)
            except Exception:
                break

    pump = asyncio.create_task(_pump())
    try:
        while True:
            # keep socket alive; ignore client messages for now
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        pump.cancel()
        try:
            await pubsub.unsubscribe()
            await pubsub.close()
        except Exception:
            pass
