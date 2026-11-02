import pytest

from workstation.dcf import calculate, independent_check
from workstation.schemas import Assumptions, Financials


@pytest.fixture
def assumptions():
    return Assumptions(wacc=0.1, growth=0, terminal_growth=0, fcff_margin=0.1, years=5)


def test_constant_perpetuity(financials, assumptions):
    result = calculate(financials, assumptions)
    assert result["enterprise_value"] == pytest.approx(1_000_000_000)
    assert result["equity_value"] == pytest.approx(950_000_000)
    assert result["fair_value"] == pytest.approx(95)
    checked = independent_check(financials, assumptions, result, 0.03)
    assert len(checked["sensitivity"]) == 9
    assert set(checked["scenarios"]) == {"bear", "base", "bull"}
    assert checked["scenarios"]["bear"]["result"]["fair_value"] < result["fair_value"]
    assert checked["scenarios"]["bull"]["result"]["fair_value"] > result["fair_value"]


@pytest.mark.parametrize(
    "updates", [{"terminal_growth": 0.04}, {"wacc": 0.02, "terminal_growth": 0.02}]
)
def test_terminal_failures(financials, assumptions, updates):
    with pytest.raises(ValueError, match="Terminal growth"):
        calculate(financials, assumptions.model_copy(update=updates))


@pytest.mark.parametrize(
    "metric,field,value",
    [
        ("shares", "value", -1),
        ("shares", "value", 0),
        ("shares", "value", float("nan")),
        ("revenue", "unit", "millions"),
        ("cash", "currency", "EUR"),
        ("fcff", "value", -100),
        ("price", "value", 0),
        ("debt", "source", ""),
    ],
)
def test_bad_inputs(financials, metric, field, value):
    raw = financials.model_dump()
    raw["data"][metric][field] = value
    with pytest.raises(ValueError):
        Financials.model_validate(raw)


def test_missing_data(financials):
    raw = financials.model_dump()
    del raw["data"]["fcff"]
    with pytest.raises(ValueError, match="Missing data"):
        Financials.model_validate(raw)


def test_terminal_flag_and_independent_mismatch(financials, assumptions):
    a = assumptions.model_copy(update={"years": 1})
    calc = calculate(financials, a)
    assert calc["terminal_share"] > 0.75 and calc["warnings"]
    calc["equity_value"] += 500
    with pytest.raises(ValueError, match="disagrees"):
        independent_check(financials, a, calc, 0.03)
