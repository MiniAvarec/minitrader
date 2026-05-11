from __future__ import annotations

from dataclasses import dataclass


DEFAULT_TAKER_FEES = {
    "binance": 0.0004,
    "okx": 0.0005,
    "bybit": 0.00055,
}


@dataclass(slots=True)
class RouteCandidate:
    exchange: str
    symbol: str
    ok: bool
    expected_price: float | None = None
    mark_price: float | None = None
    spread_bps: float | None = None
    slippage_bps: float | None = None
    fee_usdt: float | None = None
    total_cost_usdt: float | None = None
    reason: str = "ok"


def estimate_market_fill(order_book: dict, side: str, notional_usdt: float) -> tuple[float, float]:
    levels = order_book.get("asks" if side == "buy" else "bids") or []
    if not levels:
        raise ValueError("empty order book side")
    remaining = float(notional_usdt)
    qty = 0.0
    cost = 0.0
    for price_raw, qty_raw, *_ in levels:
        price = float(price_raw)
        available_qty = float(qty_raw)
        if price <= 0 or available_qty <= 0:
            continue
        level_cost = price * available_qty
        take_cost = min(remaining, level_cost)
        take_qty = take_cost / price
        qty += take_qty
        cost += take_cost
        remaining -= take_cost
        if remaining <= 1e-9:
            break
    if remaining > max(1.0, notional_usdt * 0.01):
        raise ValueError("insufficient visible liquidity")
    if qty <= 0:
        raise ValueError("could not estimate fill")
    return cost / qty, qty


def score_order_book(
    *,
    exchange: str,
    symbol: str,
    order_book: dict,
    side: str,
    notional_usdt: float,
    fee_rate: float | None = None,
) -> RouteCandidate:
    try:
        expected_price, _ = estimate_market_fill(order_book, side, notional_usdt)
        bid = float((order_book.get("bids") or [[0]])[0][0] or 0)
        ask = float((order_book.get("asks") or [[0]])[0][0] or 0)
        if bid <= 0 or ask <= 0:
            raise ValueError("missing top of book")
        mid = (bid + ask) / 2
        spread_bps = ((ask - bid) / mid) * 10_000 if mid > 0 else 0.0
        if side == "buy":
            slippage_bps = max(0.0, ((expected_price - ask) / ask) * 10_000)
        else:
            slippage_bps = max(0.0, ((bid - expected_price) / bid) * 10_000)
        rate = DEFAULT_TAKER_FEES.get(exchange, 0.0005) if fee_rate is None else fee_rate
        fee = notional_usdt * rate
        total = fee + (notional_usdt * (spread_bps + slippage_bps) / 10_000)
        return RouteCandidate(
            exchange=exchange,
            symbol=symbol,
            ok=True,
            expected_price=expected_price,
            mark_price=mid,
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
            fee_usdt=fee,
            total_cost_usdt=total,
        )
    except Exception as e:
        return RouteCandidate(exchange=exchange, symbol=symbol, ok=False, reason=str(e))


def best_candidate(candidates: list[RouteCandidate]) -> RouteCandidate | None:
    valid = [c for c in candidates if c.ok and c.total_cost_usdt is not None]
    if not valid:
        return None
    return min(valid, key=lambda c: c.total_cost_usdt or float("inf"))

