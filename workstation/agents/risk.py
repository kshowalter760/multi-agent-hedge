import json

from ..dcf import independent_check
from ..provenance import render_narrative
from ..schemas import RiskOutput
from .common import prompt


async def run(provider, financials, assumptions, reported, analyst_memo, config):
    checks = independent_check(financials, assumptions, reported, config.terminal_growth_bound)
    system, version = prompt("risk")
    output = await provider.generate(
        "risk",
        system,
        {
            "untrusted_financials": financials.model_dump(mode="json"),
            "analyst_assumptions": assumptions.model_dump(),
            "analyst_memo": analyst_memo,
            "independent_checks": checks,
        },
        RiskOutput,
    )
    memo = render_narrative(output.reasons, financials, assumptions, checks["recomputed"])
    as_of = min(d.as_of for d in financials.data.values())
    memo += (
        "\n\nIndependent recomputation, sensitivity grid and scenarios. "
        f"Source: Python risk engine; input as-of {as_of}. "
        "Scenario parameters are stress assumptions.\n\n```json\n"
        f"{json.dumps(checks, indent=2)}\n```"
    )
    return output, checks, memo, version
