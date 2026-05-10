from app.db.models import RiskConfig
from app.risk.checks import check_size, check_sl_tp


def _cfg(**over):
    cfg = RiskConfig(
        user_id=1,
        max_notional_usdt=50.0,
        daily_loss_limit_usdt=100.0,
        max_concurrent_positions=3,
        require_sl_tp=True,
    )
    for k, v in over.items():
        setattr(cfg, k, v)
    return cfg


def test_check_size_pass():
    r = check_size(40.0, _cfg())
    assert r.ok


def test_check_size_fail():
    r = check_size(80.0, _cfg())
    assert not r.ok
    assert "cap" in r.reason


def test_check_sl_tp_required_fails_when_missing():
    r = check_sl_tp(None, 100.0, _cfg())
    assert not r.ok


def test_check_sl_tp_optional_when_disabled():
    r = check_sl_tp(None, None, _cfg(require_sl_tp=False))
    assert r.ok


def test_check_sl_tp_pass():
    r = check_sl_tp(99.0, 110.0, _cfg())
    assert r.ok
