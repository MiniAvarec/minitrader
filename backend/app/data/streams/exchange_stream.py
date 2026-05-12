"""ExchangeStream: redundant kline ingestion for one exchange.

Two parallel ccxt.pro clients (PRIMARY + STANDBY) call `watch_ohlcv` for the
same subscription set. Both push bars into one queue; the consumer dedupes via
`KlineDedupeBuffer` and writes the winning bar to Redis. Gaps trigger a REST
backfill via the matching Broker.

Subscriptions are mutable — `update_subscriptions(...)` diffs against current
and rebuilds the watch tasks if the set has changed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Awaitable, Callable

from app.brokers.base import KlineMsg, to_ccxt_symbol
from app.brokers.factory import get_broker
from app.config import get_settings
from app.data.redis_io import (
    KLINE_LIMIT,
    SIGNAL_CHANNEL,
    klines_key,
    make_redis,
    push_kline,
    replace_last_kline,
)
from app.data.streams.dedupe import KlineDedupeBuffer, tf_to_ms


log = logging.getLogger("streams.exchange")


Sub = tuple[str, str]  # (native_symbol, tf)


class ExchangeStream:
    def __init__(self, exchange: str):
        self.exchange = exchange
        self.testnet = get_settings().testnet_for(exchange)
        self.subs: set[Sub] = set()
        self.queue: asyncio.Queue[KlineMsg] = asyncio.Queue(maxsize=4096)
        self.dedupe = KlineDedupeBuffer()
        self._primary_task: asyncio.Task | None = None
        self._standby_task: asyncio.Task | None = None
        self._consumer_task: asyncio.Task | None = None
        # IBKR uses an authenticated TWS/IB Gateway connection rather than
        # public-data feeds. It also rejects duplicate clientIds, so we run
        # only one broker (no standby) and pin its clientId via env.
        if exchange == "ibkr":
            cfg = {
                "host": os.environ.get("IBKR_HOST", "ibgateway"),
                "port": int(os.environ.get(
                    "IBKR_PORT", "4002" if self.testnet else "4001"
                )),
                "client_id": int(os.environ.get("IBKR_CLIENT_ID_INGESTOR", "2")),
                "account": os.environ.get("IBKR_ACCOUNT") or None,
            }
            self._primary = get_broker(
                exchange, "", "", testnet=self.testnet,
                connection_config=json.dumps(cfg),
            )
            self._standby = None
        else:
            # Two brokers (no keys needed for public klines).
            self._primary = get_broker(exchange, "", "", testnet=self.testnet)
            self._standby = get_broker(exchange, "", "", testnet=self.testnet)

    # ----- lifecycle -----

    async def start(self) -> None:
        if self._consumer_task is None:
            self._consumer_task = asyncio.create_task(self._consume())

    async def stop(self) -> None:
        for t in (self._primary_task, self._standby_task, self._consumer_task):
            if t is not None:
                t.cancel()
        close_calls = [self._primary.close()]
        if self._standby is not None:
            close_calls.append(self._standby.close())
        await asyncio.gather(*close_calls, return_exceptions=True)

    async def update_subscriptions(self, subs: set[Sub]) -> None:
        if subs == self.subs:
            return
        new_subs = subs - self.subs
        self.subs = set(subs)
        # Seed Redis with REST history for fresh subscriptions so strategies
        # have a populated rolling window from tick 0.
        if new_subs:
            await self._seed_history(sorted(new_subs))
        # Restart both watch tasks with the new subscription set.
        for t in (self._primary_task, self._standby_task):
            if t is not None:
                t.cancel()
        if not self.subs:
            self._primary_task = self._standby_task = None
            return
        subs_list = sorted(self.subs)
        self._primary_task = asyncio.create_task(self._watch(self._primary, subs_list, "primary"))
        if self._standby is not None:
            self._standby_task = asyncio.create_task(self._watch(self._standby, subs_list, "standby"))
        else:
            self._standby_task = None

    async def _seed_history(self, subs: list[Sub]) -> None:
        r = make_redis()
        for native, tf in subs:
            try:
                rows = await self._primary.fetch_klines(native, tf, limit=KLINE_LIMIT)
            except Exception as e:
                log.warning("seed %s %s %s failed: %s", self.exchange, native, tf, e)
                continue
            await r.delete(klines_key(self.exchange, native, tf))
            for row in rows:
                await push_kline(r, self.exchange, native, tf, row)
            if rows:
                self.dedupe.record(self.exchange, native, tf, int(rows[-1]["open_time"]))
            log.info("seeded %s %s %s: %d bars", self.exchange, native, tf, len(rows))

    # ----- internals -----

    async def _watch(self, broker, subs: list[Sub], label: str) -> None:
        """Run the broker's iter_klines and push bars into the shared queue."""
        while True:
            try:
                async for msg in broker.iter_klines(subs):
                    await self.queue.put(msg)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning("%s %s iter_klines crashed: %s", self.exchange, label, e)
                await asyncio.sleep(2)

    async def _consume(self) -> None:
        r = make_redis()
        while True:
            try:
                msg = await self.queue.get()
                await self._process(r, msg)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning("%s consumer error: %s", self.exchange, e)

    async def _process(self, r, msg: KlineMsg) -> None:
        verdict = self.dedupe.classify(msg.exchange, msg.symbol, msg.tf, msg.open_time)
        # ccxt.pro emits the in-progress bar repeatedly with a moving close. Treat
        # `closed=False` updates that share open_time with the last published bar
        # as "live tail" → replace_last (not push).
        last_seen = self.dedupe.last_open.get((msg.exchange, msg.symbol, msg.tf))
        norm = _to_dict(msg)

        if verdict == "duplicate" and last_seen == msg.open_time:
            # In-progress update of the same bar — refresh tail.
            await replace_last_kline(r, msg.exchange, msg.symbol, msg.tf, norm)
            return
        if verdict == "duplicate":
            return

        if verdict == "gap":
            await self._backfill_gap(r, msg)

        await push_kline(r, msg.exchange, msg.symbol, msg.tf, norm)
        self.dedupe.record(msg.exchange, msg.symbol, msg.tf, msg.open_time)

        # Notify downstream consumers (signals worker) once the bar is settled.
        if msg.closed:
            await r.publish(
                SIGNAL_CHANNEL,
                _kline_closed_payload(msg),
            )

    async def _backfill_gap(self, r, msg: KlineMsg) -> None:
        prev_open = self.dedupe.last_open.get((msg.exchange, msg.symbol, msg.tf))
        if prev_open is None:
            return
        step = tf_to_ms(msg.tf)
        try:
            rows = await self._primary.fetch_klines(
                msg.symbol, msg.tf, end_ms=msg.open_time, limit=500
            )
        except Exception as e:
            log.warning(
                "backfill failed %s %s %s: %s", msg.exchange, msg.symbol, msg.tf, e
            )
            return
        # Insert only the bars that fall strictly between prev_open and msg.open_time.
        for row in rows:
            ot = int(row["open_time"])
            if ot <= prev_open or ot >= msg.open_time:
                continue
            await push_kline(r, msg.exchange, msg.symbol, msg.tf, row)
            self.dedupe.record(msg.exchange, msg.symbol, msg.tf, ot)
        log.info(
            "backfilled gap %s %s %s prev=%s now=%s",
            msg.exchange, msg.symbol, msg.tf, prev_open, msg.open_time,
        )


def _to_dict(msg: KlineMsg) -> dict:
    return {
        "open_time": msg.open_time,
        "close_time": msg.close_time,
        "open": msg.open,
        "high": msg.high,
        "low": msg.low,
        "close": msg.close,
        "volume": msg.volume,
        "closed": msg.closed,
    }


def _kline_closed_payload(msg: KlineMsg) -> str:
    import json
    return json.dumps(
        {
            "event": "kline_closed",
            "exchange": msg.exchange,
            "symbol": msg.symbol,
            "tf": msg.tf,
        }
    )
