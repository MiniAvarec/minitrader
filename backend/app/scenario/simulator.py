from __future__ import annotations


def simulate(
    positions: list[dict],
    *,
    price_shocks: dict[str, float],
    daily_realized_pnl_usdt: float = 0.0,
    daily_loss_limit_usdt: float = 100.0,
) -> dict:
    impacts: list[dict] = []
    total = 0.0
    for p in positions:
        symbol = str(p.get("symbol") or "")
        base = _base(symbol)
        shock = price_shocks.get(symbol, price_shocks.get(base, price_shocks.get("*", 0.0)))
        notional = abs(float(p.get("notional") or 0.0))
        side = str(p.get("side") or "long").lower()
        signed = notional * shock
        if side not in {"long", "buy"}:
            signed *= -1
        total += signed
        impacts.append(
            {
                "symbol": symbol,
                "base": base,
                "side": side,
                "shock_pct": shock,
                "notional_usdt": notional,
                "pnl_usdt": signed,
            }
        )
    projected_daily = daily_realized_pnl_usdt + total
    usage = abs(min(0.0, projected_daily)) / daily_loss_limit_usdt if daily_loss_limit_usdt > 0 else 0.0
    return {
        "positions": impacts,
        "total_pnl_usdt": total,
        "projected_daily_pnl_usdt": projected_daily,
        "daily_loss_limit_usdt": daily_loss_limit_usdt,
        "daily_loss_usage": usage,
        "daily_loss_breached": projected_daily <= -daily_loss_limit_usdt,
        "max_drawdown_estimate_pct": usage,
    }


def preset_shocks(preset: str, magnitude_pct: float) -> dict[str, float]:
    mag = magnitude_pct / 100.0
    if preset == "gap_down":
        return {"*": -abs(mag)}
    if preset == "gap_up":
        return {"*": abs(mag)}
    if preset == "volatility_cascade":
        return {"*": -abs(mag) * 1.5}
    if preset == "stop_series":
        return {"*": -abs(mag)}
    if preset == "correlation_spike":
        return {"*": -abs(mag)}
    return {"*": mag}


def _base(symbol: str) -> str:
    unified = symbol.split(":")[0]
    if "/" in unified:
        return unified.split("/")[0].upper()
    compact = unified.replace("-", "")
    return compact[:-4].upper() if compact.endswith("USDT") else compact.upper()

