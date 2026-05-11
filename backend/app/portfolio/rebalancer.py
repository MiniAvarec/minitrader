from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PositionExposure:
    exchange: str
    symbol: str
    base: str
    side: str
    notional_usdt: float
    contracts: float
    mark_price: float


def base_from_symbol(symbol: str) -> str:
    unified = symbol.split(":")[0]
    if "/" in unified:
        return unified.split("/")[0].upper()
    compact = unified.replace("-", "")
    return compact[:-4].upper() if compact.endswith("USDT") else compact.upper()


def normalize_position(exchange: str, raw: dict) -> PositionExposure | None:
    notional = abs(float(raw.get("notional") or 0.0))
    contracts = abs(float(raw.get("contracts") or 0.0))
    if notional <= 0 and contracts <= 0:
        return None
    symbol = str(raw.get("symbol") or "")
    mark = float(raw.get("mark_price") or raw.get("markPrice") or 0.0)
    if notional <= 0 and mark > 0:
        notional = contracts * mark
    side = str(raw.get("side") or "long").lower()
    return PositionExposure(
        exchange=exchange,
        symbol=symbol,
        base=base_from_symbol(symbol),
        side=side,
        notional_usdt=notional,
        contracts=contracts,
        mark_price=mark,
    )


def build_plan(
    positions: list[PositionExposure],
    *,
    max_exchange_share: float = 0.60,
    max_asset_share: float = 0.50,
    min_order_notional_usdt: float = 10.0,
) -> dict:
    total = sum(p.notional_usdt for p in positions)
    by_exchange: dict[str, float] = {}
    by_asset: dict[str, float] = {}
    for p in positions:
        by_exchange[p.exchange] = by_exchange.get(p.exchange, 0.0) + p.notional_usdt
        by_asset[p.base] = by_asset.get(p.base, 0.0) + p.notional_usdt

    intents: list[dict] = []
    if total > 0:
        for exchange, exposure in by_exchange.items():
            excess = exposure - total * max_exchange_share
            if excess > min_order_notional_usdt:
                intents.extend(
                    _reduce_intents(
                        [p for p in positions if p.exchange == exchange],
                        excess,
                        f"exchange_share>{max_exchange_share:.2f}",
                    )
                )
        for base, exposure in by_asset.items():
            excess = exposure - total * max_asset_share
            if excess > min_order_notional_usdt:
                intents.extend(
                    _reduce_intents(
                        [p for p in positions if p.base == base],
                        excess,
                        f"asset_share>{max_asset_share:.2f}",
                    )
                )

    deduped: dict[tuple[str, str, str], dict] = {}
    caps = {
        (p.exchange, p.symbol, "sell" if p.side in {"long", "buy"} else "buy"): p
        for p in positions
    }
    for intent in intents:
        key = (intent["exchange"], intent["symbol"], intent["side"])
        current = deduped.get(key)
        if current is None:
            deduped[key] = intent
        else:
            current["notional_usdt"] += intent["notional_usdt"]
            current["qty"] += intent["qty"]
            current["reason"] = f'{current["reason"]}, {intent["reason"]}'
    for key, intent in deduped.items():
        cap = caps.get(key)
        if cap is not None and intent["notional_usdt"] > cap.notional_usdt:
            intent["notional_usdt"] = cap.notional_usdt
            intent["qty"] = cap.contracts

    return {
        "total_exposure_usdt": total,
        "by_exchange": by_exchange,
        "by_asset": by_asset,
        "intents": list(deduped.values()),
        "warnings": [] if total > 0 else ["no open exposure"],
    }


def _reduce_intents(positions: list[PositionExposure], excess: float, reason: str) -> list[dict]:
    out: list[dict] = []
    remaining = excess
    for p in sorted(positions, key=lambda x: x.notional_usdt, reverse=True):
        if remaining <= 0:
            break
        notional = min(p.notional_usdt, remaining)
        side = "sell" if p.side in {"long", "buy"} else "buy"
        qty = notional / p.mark_price if p.mark_price > 0 else p.contracts
        out.append(
            {
                "exchange": p.exchange,
                "symbol": p.symbol,
                "base": p.base,
                "side": side,
                "notional_usdt": notional,
                "qty": qty,
                "reduce_only": True,
                "reason": reason,
            }
        )
        remaining -= notional
    return out
