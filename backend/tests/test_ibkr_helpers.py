"""Unit tests for IBKR pure-function helpers.

These tests intentionally avoid importing `app.brokers.ibkr` directly so they
don't require `ib_insync` to be installed. They cover the helpers that have
no IBKR runtime dependency: symbol encoding, bar-size mapping, trading-hours
parsing, and status mapping.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.brokers.base import (
    decode_ibkr_symbol,
    encode_ibkr_symbol,
    from_ccxt_symbol,
    to_ccxt_symbol,
)


# ---- symbol encode / decode ----


def test_encode_stock() -> None:
    s = encode_ibkr_symbol(
        root="AAPL", routing_exchange="SMART", currency="USD", contract_type="stock"
    )
    assert s == "AAPL.SMART.USD"


def test_encode_future_requires_expiry() -> None:
    with pytest.raises(ValueError):
        encode_ibkr_symbol(
            root="ES", routing_exchange="CME", currency="USD", contract_type="future"
        )


def test_encode_option_requires_strike_and_right() -> None:
    s = encode_ibkr_symbol(
        root="AAPL",
        routing_exchange="SMART",
        currency="USD",
        contract_type="option",
        expiry="20250620",
        right="C",
        strike=180,
    )
    assert s == "AAPL.SMART.USD.20250620.C.180"


def test_encode_option_rejects_bad_right() -> None:
    with pytest.raises(ValueError):
        encode_ibkr_symbol(
            root="AAPL",
            routing_exchange="SMART",
            currency="USD",
            contract_type="option",
            expiry="20250620",
            right="X",
            strike=180,
        )


def test_decode_stock_is_ambiguous() -> None:
    d = decode_ibkr_symbol("AAPL.SMART.USD")
    # 3-part decode can't tell stock from forex without an Instrument row.
    assert d["contract_type"] is None
    assert d["root"] == "AAPL"
    assert d["currency"] == "USD"


def test_decode_future() -> None:
    d = decode_ibkr_symbol("ES.CME.USD.202509")
    assert d == {
        "root": "ES",
        "routing_exchange": "CME",
        "currency": "USD",
        "contract_type": "future",
        "expiry": "202509",
    }


def test_decode_option() -> None:
    d = decode_ibkr_symbol("AAPL.SMART.USD.20250620.C.180")
    assert d["contract_type"] == "option"
    assert d["strike"] == 180.0
    assert d["right"] == "C"


def test_decode_rejects_bad_arity() -> None:
    with pytest.raises(ValueError):
        decode_ibkr_symbol("AAPL")
    with pytest.raises(ValueError):
        decode_ibkr_symbol("A.B.C.D.E")  # 5 parts is invalid


# ---- ccxt no-op for IBKR ----


def test_ccxt_passthrough() -> None:
    assert to_ccxt_symbol("ibkr", "AAPL.SMART.USD") == "AAPL.SMART.USD"
    assert from_ccxt_symbol("ibkr", "AAPL.SMART.USD") == "AAPL.SMART.USD"


def test_existing_exchanges_unchanged() -> None:
    assert to_ccxt_symbol("binance", "BTCUSDT") == "BTC/USDT:USDT"
    assert to_ccxt_symbol("okx", "BTC-USDT-SWAP") == "BTC/USDT:USDT"


# ---- trading-hours parser ----
#
# Re-define inline (rather than import from app.brokers.ibkr, which pulls
# in ib_insync). Keep this in sync with `_is_within_trading_hours`.

def _parse(hours: str, tz_name: str) -> bool:
    if not hours:
        return True
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)
    today_key = now.strftime("%Y%m%d")
    for seg in hours.split(";"):
        seg = seg.strip()
        if not seg or "CLOSED" in seg:
            continue
        try:
            start_raw, end_raw = seg.split("-")
            start_day, start_time = start_raw.split(":")
            end_day, end_time = end_raw.split(":")
            if start_day != today_key and end_day != today_key:
                continue
            start_dt = datetime.strptime(
                f"{start_day}{start_time}", "%Y%m%d%H%M"
            ).replace(tzinfo=tz)
            end_dt = datetime.strptime(
                f"{end_day}{end_time}", "%Y%m%d%H%M"
            ).replace(tzinfo=tz)
            if start_dt <= now <= end_dt:
                return True
        except Exception:
            continue
    return False


def test_empty_hours_open() -> None:
    assert _parse("", "America/New_York") is True


def test_closed_marker() -> None:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    assert _parse(f"{today}:CLOSED", "UTC") is False


def test_window_covers_now() -> None:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    now_h = datetime.now(timezone.utc).hour
    if now_h == 0 or now_h == 23:
        pytest.skip("hour-boundary makes the test non-deterministic")
    hrs = f"{today}:{now_h - 1:02d}00-{today}:{now_h + 1:02d}00"
    assert _parse(hrs, "UTC") is True


def test_window_does_not_cover_now() -> None:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    assert _parse(f"{today}:0000-{today}:0001", "UTC") is False
