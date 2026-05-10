from pathlib import Path

import pytest

from app.signals.dsl.loader import StrategyParseError, load_yaml_file, load_yaml_text

BUILTINS = Path(__file__).resolve().parent.parent / "app" / "signals" / "dsl" / "builtins"


@pytest.mark.parametrize("path", sorted(BUILTINS.glob("*.yaml")))
def test_all_builtins_parse(path):
    strat = load_yaml_file(path)
    assert strat.name
    assert strat.entry.long is not None or strat.entry.short is not None


def test_unknown_op_rejected():
    with pytest.raises(StrategyParseError) as e:
        load_yaml_text(
            """
            name: bad
            entry:
              long: { lhs: 1, op: lessthan, rhs: 2 }
            sl: { atr_mult: 1.0 }
            tp: { atr_mult: 2.0 }
            """
        )
    assert "lessthan" in str(e.value)


def test_unknown_indicator_rejected():
    with pytest.raises(StrategyParseError) as e:
        load_yaml_text(
            """
            name: bad
            entry:
              long: { lhs: { foo: ["15m"] }, op: ">", rhs: 0 }
            sl: { atr_mult: 1.0 }
            tp: { atr_mult: 2.0 }
            """
        )
    assert "unknown indicator" in str(e.value)


def test_param_must_be_declared():
    with pytest.raises(StrategyParseError) as e:
        load_yaml_text(
            """
            name: bad
            params: { a: 1 }
            entry:
              long:
                lhs: { rsi: ["15m", 14] }
                op: "<"
                rhs: { param: nope }
            sl: { atr_mult: 1.0 }
            tp: { atr_mult: 2.0 }
            """
        )
    assert "param" in str(e.value).lower()


def test_sl_tp_must_have_one_of_atr_or_pct():
    with pytest.raises(StrategyParseError):
        load_yaml_text(
            """
            name: bad
            entry:
              long: { lhs: 1, op: ">", rhs: 0 }
            sl: { }
            tp: { atr_mult: 1.0 }
            """
        )


def test_yaml_syntax_error_reported():
    with pytest.raises(StrategyParseError):
        load_yaml_text("not: valid: yaml: ::::")


def test_entry_must_have_long_or_short():
    with pytest.raises(StrategyParseError):
        load_yaml_text(
            """
            name: bad
            entry: {}
            sl: { atr_mult: 1.0 }
            tp: { atr_mult: 2.0 }
            """
        )


def test_max_depth_enforced():
    deeply = "lhs: 1, op: '<', rhs: 0"
    body = "{ all_of: [{ all_of: [{ all_of: [{ all_of: [{ all_of: [{ all_of: [{ " + deeply + " }] }] }] }] }] }] }"
    with pytest.raises(StrategyParseError) as e:
        load_yaml_text(
            f"""
            name: deep
            entry:
              long: {body}
            sl: {{ atr_mult: 1.0 }}
            tp: {{ atr_mult: 2.0 }}
            """
        )
    assert "depth" in str(e.value).lower()
