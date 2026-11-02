import re

from .schemas import Assumptions, Financials

DISCLAIMER = "Research and education tool only; not financial advice. Paper trading only."
REF = re.compile(r"\{\{(data|calc|assumption)\.([a-z_]+)\}\}")
NUMBER_WORDS = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|"
    r"forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|"
    r"trillion|percent|percentage|half|quarter|double|triple)\b",
    re.I,
)


def render_narrative(text: str, f: Financials, a: Assumptions, calc: dict) -> str:
    """Reject literal numbers, unknown refs, external citations, and hidden markup.

    Numbers are inserted by code only. Qualitative prose still requires human review.
    """
    remainder = REF.sub("", text)
    if (
        any(c.isnumeric() for c in remainder)
        or NUMBER_WORDS.search(remainder)
        or re.search(r"[{}<>\[\]]|https?://|www\.", remainder)
    ):
        raise ValueError(
            "Unprovenanced number/citation or markup in narrative; use named references"
        )
    as_of = min(item.as_of for item in f.data.values()).isoformat()

    def replace(match):
        kind, name = match.groups()
        if kind == "data":
            if name not in f.data:
                raise ValueError(f"Unknown data citation: {name}")
            d = f.data[name]
            return f"{d.value:,.6g} {d.currency} {d.unit} (source: {d.source}; as-of {d.as_of})"
        values = a.model_dump() if kind == "assumption" else calc
        if name not in values or not isinstance(values[name], (int, float)):
            raise ValueError(f"Unknown numerical reference: {kind}.{name}")
        source = (
            "agent forecast assumption, not observed data"
            if kind == "assumption"
            else "deterministic DCF using cited inputs and assumptions"
        )
        return f"{values[name]:,.6g} (source: {source}; input as-of {as_of})"

    return REF.sub(replace, text)


def evidence_table(f: Financials, a: Assumptions, calc: dict) -> str:
    lines = [
        "## Input provenance",
        "",
        "Metric | Value | Unit | Currency | Source | As-of",
        "--- | ---: | --- | --- | --- | ---",
    ]
    for name, d in f.data.items():
        source = d.source.replace("|", "\\|").replace("\n", " ")
        lines.append(f"{name} | {d.value:.10g} | {d.unit} | {d.currency} | {source} | {d.as_of}")
    as_of = min(d.as_of for d in f.data.values())
    lines += [
        "",
        "## Forecast assumptions",
        "",
        "These are hypothetical agent assumptions, not fetched facts.",
        "",
    ]
    lines += [
        f"- {k}: {v} (source: analyst assumption; input as-of {as_of})"
        for k, v in a.model_dump().items()
    ]
    lines += ["", "## Deterministic DCF", ""]
    lines += [
        f"- {k}: {v} (source: Python DCF over inputs above; input as-of {as_of})"
        for k, v in calc.items()
    ]
    return "\n".join(lines)
