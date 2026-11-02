from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from .config import StrictModel


class Datum(StrictModel):
    value: float
    unit: str
    currency: str
    source: str = Field(min_length=1)
    as_of: date


class Financials(StrictModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    sector: str = Field(min_length=1)
    data: dict[str, Datum]
    untrusted_text: str = ""

    @model_validator(mode="after")
    def consistent(self):
        required = {"revenue", "fcff", "cash", "debt", "shares", "price"}
        missing = required - self.data.keys()
        if missing:
            raise ValueError(f"Missing data; cannot guess: {sorted(missing)}")
        currencies = {v.currency for v in self.data.values()}
        if len(currencies) != 1:
            raise ValueError("Mixed currency inputs")
        for name, item in self.data.items():
            expected = (
                "shares" if name == "shares" else "per_share" if name == "price" else "currency"
            )
            if item.unit != expected:
                raise ValueError(f"{name}: expected absolute {expected} units (not millions)")
            if item.as_of > date.today():
                raise ValueError("Future-dated source")
        if self.data["shares"].value <= 0 or self.data["price"].value <= 0:
            raise ValueError("Share count and price must be positive")
        if self.data["revenue"].value <= 0 or self.data["fcff"].value <= 0:
            raise ValueError("This DCF requires positive revenue and FCFF")
        if self.data["cash"].value < 0 or self.data["debt"].value < 0:
            raise ValueError("Cash and debt cannot be negative")
        return self


class Assumptions(StrictModel):
    wacc: float = Field(gt=0, le=0.5)
    growth: float = Field(ge=-0.5, le=0.5)
    terminal_growth: float = Field(ge=-0.05, le=0.05)
    fcff_margin: float = Field(gt=0, le=1)
    years: int = Field(default=5, ge=1, le=10)


class AnalystOutput(StrictModel):
    assumptions: Assumptions
    narrative: str = Field(min_length=1, max_length=6000)


class RiskOutput(StrictModel):
    verdict: Literal["approve", "request_changes", "reject"]
    reasons: str = Field(min_length=1, max_length=6000)


class PMOutput(StrictModel):
    action: Literal["buy", "sell", "hold"]
    weight: float = Field(ge=0, le=1, description="Trade notional fraction of current NAV")
    limit_price: float = Field(gt=0, description="Explicit hypothetical price limit assumption")
    narrative: str = Field(min_length=1, max_length=6000)


class SeniorOutput(StrictModel):
    verdict: Literal["approve", "request_changes", "reject"]
    reasons: str = Field(min_length=1, max_length=6000)
