"""Helpers to round qty/price to the venue's lot_size / tick_size."""
from __future__ import annotations

import math
from typing import Optional

from app.db.models import Instrument


def round_qty(qty: float, instrument: Optional[Instrument]) -> float:
    if instrument is None or not instrument.lot_size:
        return round(qty, 6)
    step = instrument.lot_size
    # Floor to nearest lot_size to avoid overspending.
    return math.floor(qty / step) * step


def round_price(price: float, instrument: Optional[Instrument]) -> float:
    if instrument is None or not instrument.tick_size:
        return round(price, 6)
    step = instrument.tick_size
    return round(price / step) * step
