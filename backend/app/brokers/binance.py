"""Async Binance USDT-M Futures broker (ccxt)."""
from __future__ import annotations

import ccxt.async_support as ccxt


class BinanceBroker:
    def __init__(self, api_key: str, api_secret: str, *, testnet: bool = True):
        self.client = ccxt.binanceusdm(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
            }
        )
        if testnet:
            self.client.set_sandbox_mode(True)

    async def usdt_balance(self) -> float:
        bal = await self.client.fetch_balance()
        return float(bal.get("USDT", {}).get("free", 0.0))

    async def positions(self) -> list[dict]:
        raw = await self.client.fetch_positions()
        out: list[dict] = []
        for p in raw:
            contracts = float(p.get("contracts") or 0.0)
            if contracts == 0:
                continue
            out.append(
                {
                    "symbol": p.get("symbol"),
                    "side": p.get("side"),
                    "contracts": contracts,
                    "notional": float(p.get("notional") or 0.0),
                    "entry_price": float(p.get("entryPrice") or 0.0),
                    "mark_price": float(p.get("markPrice") or 0.0),
                    "unrealized_pnl": float(p.get("unrealizedPnl") or 0.0),
                    "leverage": float(p.get("leverage") or 0.0),
                }
            )
        return out

    async def mark_price(self, symbol: str) -> float:
        t = await self.client.fetch_ticker(symbol)
        return float(t.get("last") or t.get("close") or 0.0)

    async def place_market(
        self,
        symbol: str,
        side: str,
        qty: float,
        *,
        sl: float | None = None,
        tp: float | None = None,
        reduce_only: bool = False,
    ) -> dict:
        params: dict = {}
        if reduce_only:
            params["reduceOnly"] = True
        order = await self.client.create_order(symbol, "market", side, qty, None, params)
        # Bracket: separate STOP_MARKET (SL) and TAKE_PROFIT_MARKET (TP), reduce-only.
        opp = "sell" if side == "buy" else "buy"
        if sl:
            await self.client.create_order(
                symbol, "STOP_MARKET", opp, qty, None,
                {"stopPrice": sl, "reduceOnly": True, "workingType": "MARK_PRICE"},
            )
        if tp:
            await self.client.create_order(
                symbol, "TAKE_PROFIT_MARKET", opp, qty, None,
                {"stopPrice": tp, "reduceOnly": True, "workingType": "MARK_PRICE"},
            )
        return order

    async def close(self) -> None:
        try:
            await self.client.close()
        except Exception:
            pass
