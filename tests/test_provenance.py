import asyncio

import pytest

from workstation.dcf import calculate
from workstation.provenance import render_narrative
from workstation.schemas import Assumptions


@pytest.mark.parametrize(
    "text",
    [
        "Revenue is 999 dollars",
        "Revenue is nine billion",
        "{{data.invented}}",
        "{{calc.invented}}",
        "See https://fake.example",
        "<script>bad</script>",
        "Revenue １２３",
    ],
)
def test_unprovenanced_numbers_rejected(financials, text):
    a = Assumptions(wacc=0.1, growth=0.05, terminal_growth=0.02, fcff_margin=0.1)
    with pytest.raises(ValueError):
        render_narrative(text, financials, a, calculate(financials, a))


def test_cited_derived_and_observed_figures(financials):
    a = Assumptions(wacc=0.1, growth=0.05, terminal_growth=0.02, fcff_margin=0.1)
    text = render_narrative(
        "Revenue {{data.revenue}}; value {{calc.fair_value}}; discount {{assumption.wacc}}",
        financials,
        a,
        calculate(financials, a),
    )
    assert "Synthetic educational fixture" in text
    assert "as-of" in text and "deterministic DCF" in text and "not observed data" in text


def test_bad_narrative_never_staged(ws):
    generate = ws.provider.generate

    async def bad(*args):
        output = await generate(*args)
        output.narrative = "Revenue is 123456789"
        return output

    ws.provider.generate = bad
    with pytest.raises(ValueError, match="Unprovenanced"):
        asyncio.run(ws.analyze("DEMO"))
    assert ws.store.status()["proposals"] == []
