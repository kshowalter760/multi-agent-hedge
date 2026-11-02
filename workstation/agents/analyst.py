from ..dcf import calculate
from ..provenance import evidence_table, render_narrative
from ..schemas import AnalystOutput
from .common import prompt


async def run(provider, financials, config):
    system, version = prompt("analyst")
    output = await provider.generate(
        "analyst",
        system,
        {"untrusted_financials": financials.model_dump(mode="json")},
        AnalystOutput,
    )
    calc = calculate(financials, output.assumptions, config.terminal_growth_bound)
    memo = render_narrative(output.narrative, financials, output.assumptions, calc)
    memo += "\n\n" + evidence_table(financials, output.assumptions, calc)
    return output, calc, memo, version
