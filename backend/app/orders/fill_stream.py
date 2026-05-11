"""Per-(user, exchange) user-data WS subscriber.

PRIMARY path for order fill detection. Listens to `iter_user_data()` from each
user's broker and updates the matching `Order` row in real time. The 30-second
REST polling in `tracker.py` becomes the BACKUP — if a fill arrives only via
the tracker, that means this stream missed it and tracker logs `gap_found`.

Heartbeats land in Redis `fillstream:hb:{user_id}:{exchange}` so the tracker
can tell whether the primary is alive.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import Broker, FillEvent
from app.brokers.factory import get_broker_for_user
from app.data.redis_io import KEYS_CHANGED_CHANNEL, make_redis, subscribe
from app.db.models import ApiKey, Order
from app.db.session import SessionLocal


log = logging.getLogger("fill_stream")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)


HEARTBEAT_INTERVAL_S = 10


async def _apply_fill(db: AsyncSession, evt: FillEvent, user_id: int) -> None:
    row = (
        await db.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .where(Order.exchange == evt.exchange)
            .where(Order.exchange_order_id == evt.exchange_order_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return
    if evt.avg_price > 0:
        row.entry_price = evt.avg_price
    if evt.realized_pnl:
        row.realized_pnl_usdt = evt.realized_pnl
    if evt.status in {"filled", "canceled", "rejected"}:
        row.status = "closed"
        row.closed_at = datetime.now(timezone.utc)
    elif evt.status == "partially_filled":
        row.status = "partial"
    await db.commit()
    log.info(
        "fill user=%s exchange=%s order=%s status=%s pnl=%.2f",
        user_id, evt.exchange, row.id, evt.status, evt.realized_pnl,
    )


async def _run_for_user_exchange(user_id: int, exchange: str) -> None:
    r = make_redis()
    while True:
        broker: Broker | None = None
        try:
            async with SessionLocal() as db:
                broker = await get_broker_for_user(db, user_id, exchange)
            if broker is None:
                log.info("no key for user=%s exchange=%s; sleeping", user_id, exchange)
                await asyncio.sleep(30)
                continue
            log.info("subscribing user=%s exchange=%s", user_id, exchange)

            async def _hb():
                while True:
                    await r.set(
                        f"fillstream:hb:{user_id}:{exchange}",
                        str(datetime.now(timezone.utc).timestamp()),
                        ex=HEARTBEAT_INTERVAL_S * 6,
                    )
                    await asyncio.sleep(HEARTBEAT_INTERVAL_S)

            hb_task = asyncio.create_task(_hb())
            try:
                async for evt in broker.iter_user_data():
                    async with SessionLocal() as db:
                        await _apply_fill(db, evt, user_id)
            finally:
                hb_task.cancel()
        except asyncio.CancelledError:
            return
        except Exception as e:
            log.warning("user=%s exchange=%s stream crashed: %s", user_id, exchange, e)
            await asyncio.sleep(5)
        finally:
            if broker is not None:
                try:
                    await broker.close()
                except Exception:
                    pass


class FillStreamManager:
    def __init__(self):
        self.tasks: dict[tuple[int, str], asyncio.Task] = {}

    async def _desired(self) -> set[tuple[int, str]]:
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    select(ApiKey.user_id, ApiKey.exchange).where(
                        ApiKey.label == "default"
                    )
                )
            ).all()
        return set(rows)

    async def _reconcile(self) -> None:
        desired = await self._desired()
        for key in list(self.tasks):
            if key not in desired:
                log.info("stopping fill stream for %s", key)
                self.tasks.pop(key).cancel()
        for key in desired:
            if key not in self.tasks:
                user_id, exchange = key
                log.info("starting fill stream for %s", key)
                self.tasks[key] = asyncio.create_task(
                    _run_for_user_exchange(user_id, exchange)
                )

    async def main(self) -> None:
        await self._reconcile()
        r = make_redis()
        pubsub = await subscribe(r, [KEYS_CHANGED_CHANNEL])
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                payload = json.loads(msg["data"])
                log.info("keys:changed → %s", payload)
            except Exception:
                pass
            try:
                await self._reconcile()
            except Exception as e:
                log.warning("reconcile failed: %s", e)


async def main() -> None:
    await FillStreamManager().main()


if __name__ == "__main__":
    asyncio.run(main())
