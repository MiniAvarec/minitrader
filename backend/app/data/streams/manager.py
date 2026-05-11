"""Top-level streams manager.

Maintains one `ExchangeStream` per enabled exchange. The subscription set per
exchange is the union of all users' watchlists, crossed with the configured
timeframes (DEFAULT_TIMEFRAMES). Subscribes to `watchlist:changed` so adding /
removing a pair re-subscribes the corresponding ExchangeStream.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from sqlalchemy import select

from app.config import get_settings
from app.data.redis_io import WATCHLIST_CHANGED_CHANNEL, make_redis, subscribe
from app.data.streams.exchange_stream import ExchangeStream, Sub
from app.db.models import UserWatchlistEntry
from app.db.session import SessionLocal


log = logging.getLogger("streams.manager")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)


class StreamsManager:
    def __init__(self):
        self.streams: dict[str, ExchangeStream] = {}

    async def _subscription_set_by_exchange(self) -> dict[str, set[Sub]]:
        """Return {exchange: {(symbol, tf), ...}} = union of watchlists × default tfs."""
        s = get_settings()
        tfs = s.default_timeframes
        result: dict[str, set[Sub]] = defaultdict(set)
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    select(
                        UserWatchlistEntry.exchange, UserWatchlistEntry.symbol
                    ).where(UserWatchlistEntry.enabled.is_(True))
                )
            ).all()
        for exchange, symbol in rows:
            for tf in tfs:
                result[exchange].add((symbol, tf))
        return result

    async def _refresh(self) -> None:
        s = get_settings()
        target = await self._subscription_set_by_exchange()
        # Ensure a stream exists for every exchange we track (even if empty).
        for ex in s.enabled_exchanges:
            if ex not in self.streams:
                stream = ExchangeStream(ex)
                await stream.start()
                self.streams[ex] = stream
        # Push the diff to each stream.
        for ex, stream in self.streams.items():
            await stream.update_subscriptions(target.get(ex, set()))

    async def main(self) -> None:
        await self._refresh()
        log.info(
            "streams manager started; tracking %s",
            {ex: len(s.subs) for ex, s in self.streams.items()},
        )
        # Listen for watchlist changes.
        r = make_redis()
        pubsub = await subscribe(r, [WATCHLIST_CHANGED_CHANNEL])
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                payload = json.loads(msg["data"])
                log.info("watchlist:changed → %s", payload)
            except Exception:
                pass
            try:
                await self._refresh()
            except Exception as e:
                log.warning("refresh after watchlist change failed: %s", e)


async def main() -> None:
    await StreamsManager().main()


if __name__ == "__main__":
    asyncio.run(main())
