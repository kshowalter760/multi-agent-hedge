"""Deterministic unlevered FCFF DCF, in absolute currency and share units."""

from .schemas import Assumptions, Financials


def calculate(f: Financials, a: Assumptions, bound: float = 0.03) -> dict:
    if a.terminal_growth >= a.wacc:
        raise ValueError("Terminal growth must be below WACC")
    if a.terminal_growth > bound:
        raise ValueError("Terminal growth exceeds configured long-run bound")
    flows = [
        f.data["revenue"].value * (1 + a.growth) ** t * a.fcff_margin for t in range(1, a.years + 1)
    ]
    pv_flows = sum(cf / (1 + a.wacc) ** t for t, cf in enumerate(flows, 1))
    terminal = flows[-1] * (1 + a.terminal_growth) / (a.wacc - a.terminal_growth)
    pv_terminal = terminal / (1 + a.wacc) ** a.years
    ev = pv_flows + pv_terminal
    equity = ev + f.data["cash"].value - f.data["debt"].value
    share = pv_terminal / ev
    return {
        "enterprise_value": ev,
        "equity_value": equity,
        "fair_value": equity / f.data["shares"].value,
        "terminal_share": share,
        "pv_flows": pv_flows,
        "pv_terminal": pv_terminal,
        "observed_fcff_margin": f.data["fcff"].value / f.data["revenue"].value,
        "warnings": ["Terminal value exceeds seventy-five percent of EV"] if share > 0.75 else [],
    }


def independent_check(f: Financials, a: Assumptions, reported: dict, bound: float) -> dict:
    """Rebuild from raw inputs using a separate iterative implementation."""
    import math

    calculate(f, a, bound)  # Enforce shared input guards, do not reuse its numbers.
    revenue, present = f.data["revenue"].value, 0.0
    for year in range(1, a.years + 1):
        revenue *= 1 + a.growth
        flow = revenue * a.fcff_margin
        present += flow * (1 + a.wacc) ** -year
    terminal_pv = (
        flow * (1 + a.terminal_growth) / (a.wacc - a.terminal_growth) * (1 + a.wacc) ** -a.years
    )
    ev = present + terminal_pv
    equity = ev - f.data["debt"].value + f.data["cash"].value
    checks = {
        "enterprise_value": ev,
        "equity_value": equity,
        "fair_value": equity / f.data["shares"].value,
        "terminal_share": terminal_pv / ev,
        "pv_flows": present,
        "pv_terminal": terminal_pv,
        "observed_fcff_margin": f.data["fcff"].value / f.data["revenue"].value,
    }
    if any(
        not math.isclose(v, reported.get(k, float("nan")), rel_tol=1e-10, abs_tol=1e-8)
        for k, v in checks.items()
    ):
        raise ValueError("Independent risk arithmetic disagrees with analyst")
    grid = []
    for dw in (-0.02, 0, 0.02):
        for dg in (-0.01, 0, 0.01):
            values = a.model_dump() | {
                "wacc": a.wacc + dw,
                "terminal_growth": a.terminal_growth + dg,
            }
            try:
                result = calculate(f, Assumptions(**values), bound)
                grid.append(
                    {
                        "wacc": values["wacc"],
                        "terminal_growth": values["terminal_growth"],
                        "fair_value": result["fair_value"],
                    }
                )
            except ValueError:
                grid.append(
                    {
                        "wacc": values["wacc"],
                        "terminal_growth": values["terminal_growth"],
                        "invalid": "Outside DCF guardrails",
                    }
                )
    scenarios = {}
    for name, dg, dm, dw in [
        ("bear", -0.03, 0.8, 0.02),
        ("base", 0, 1, 0),
        ("bull", 0.03, 1.2, -0.01),
    ]:
        values = a.model_dump() | {
            "growth": max(-0.5, min(0.5, a.growth + dg)),
            "fcff_margin": min(1, a.fcff_margin * dm),
            "wacc": max(a.terminal_growth + 0.005, min(0.5, a.wacc + dw)),
        }
        scenarios[name] = {
            "assumptions": values,
            "result": calculate(f, Assumptions(**values), bound),
        }
    return {"recomputed": checks, "sensitivity": grid, "scenarios": scenarios}
