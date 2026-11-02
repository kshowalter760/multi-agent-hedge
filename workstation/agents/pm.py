from ..provenance import render_narrative
from ..schemas import PMOutput
from .common import prompt


async def run(
    provider, financials, assumptions, calc, analyst_memo, risk_review, portfolio, config
):
    system, version = prompt("pm")
    output = await provider.generate(
        "pm",
        system,
        {
            "financials": financials.model_dump(mode="json"),
            "analyst_memo": analyst_memo,
            "risk_review": risk_review,
            "portfolio": portfolio,
            "constraints": {
                k: getattr(config, k)
                for k in ("max_position_size", "max_sector_exposure", "cash_floor")
            },
        },
        PMOutput,
    )
    memo = render_narrative(output.narrative, financials, assumptions, calc)
    return output, memo, version
