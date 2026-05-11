import pytest

from app.execution.router import best_candidate, estimate_market_fill, score_order_book
from app.optimizer.walk_forward import expand_grid
from app.portfolio.rebalancer import build_plan, normalize_position
from app.scenario.simulator import simulate


def test_router_estimates_market_fill_across_levels():
    book = {"asks": [[100, 0.5], [101, 1.0]], "bids": [[99, 1.0]]}
    price, qty = estimate_market_fill(book, "buy", 100)
    assert qty > 0
    assert price == pytest.approx(100.4975, rel=1e-4)


def test_router_picks_lowest_total_cost_candidate():
    cheap = score_order_book(
        exchange="binance",
        symbol="BTCUSDT",
        order_book={"asks": [[100, 10]], "bids": [[99.9, 10]]},
        side="buy",
        notional_usdt=100,
        fee_rate=0.0001,
    )
    expensive = score_order_book(
        exchange="okx",
        symbol="BTC-USDT-SWAP",
        order_book={"asks": [[101, 10]], "bids": [[99, 10]]},
        side="buy",
        notional_usdt=100,
        fee_rate=0.001,
    )
    assert best_candidate([expensive, cheap]) == cheap


def test_rebalancer_generates_reduce_intent_for_overweight_exchange():
    pos = normalize_position(
        "binance",
        {"symbol": "BTC/USDT:USDT", "side": "long", "contracts": 1, "notional": 1000, "mark_price": 1000},
    )
    other = normalize_position(
        "okx",
        {"symbol": "ETH/USDT:USDT", "side": "long", "contracts": 1, "notional": 100, "mark_price": 100},
    )
    plan = build_plan([pos, other], max_exchange_share=0.6, max_asset_share=1.0)
    assert plan["intents"]
    assert plan["intents"][0]["exchange"] == "binance"
    assert plan["intents"][0]["side"] == "sell"
    assert plan["intents"][0]["reduce_only"] is True


def test_scenario_simulator_applies_side_aware_shocks():
    result = simulate(
        [
            {"symbol": "BTC/USDT:USDT", "side": "long", "notional": 1000},
            {"symbol": "ETH/USDT:USDT", "side": "short", "notional": 500},
        ],
        price_shocks={"*": -0.10},
        daily_realized_pnl_usdt=-20,
        daily_loss_limit_usdt=100,
    )
    assert result["total_pnl_usdt"] == pytest.approx(-50)
    assert result["projected_daily_pnl_usdt"] == pytest.approx(-70)
    assert result["daily_loss_usage"] == pytest.approx(0.7)


def test_optimizer_grid_expansion_is_bounded():
    rows = expand_grid({"a": [1, 2, 3], "b": [4, 5]}, max_candidates=4)
    assert len(rows) == 4
    assert rows[0] == {"a": 1, "b": 4}
