"""Deprecated shim.

The original single-exchange Binance ingestor has been replaced by
`app.data.streams.manager`. This file exists only so existing docker-compose
commands (`python -m app.data.binance_stream`) keep working until they are
updated.
"""
from __future__ import annotations

import asyncio

from app.data.streams.manager import main as _streams_main


async def main() -> None:
    await _streams_main()


if __name__ == "__main__":
    asyncio.run(main())
