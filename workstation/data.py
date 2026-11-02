import csv
import hashlib
from pathlib import Path
from typing import Protocol

from .schemas import Financials


def content_hash(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


class DataProvider(Protocol):
    def fetch(self, ticker: str) -> Financials: ...


class CSVProvider:
    """Explicit, sourced FCFF input; never silently substitute levered cash flow."""

    def __init__(self, path: Path):
        self.path = path

    def fetch(self, ticker: str) -> Financials:
        with self.path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {
                "ticker",
                "sector",
                "metric",
                "value",
                "unit",
                "currency",
                "source",
                "as_of",
            }
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f"CSV requires columns: {', '.join(sorted(required))}")
            rows = [r for r in reader if r["ticker"] == ticker]
        if not rows:
            raise ValueError(f"Missing financials for {ticker} in {self.path}")
        if len({r["sector"] for r in rows}) != 1:
            raise ValueError("Inconsistent sector")
        data = {}
        for row in rows:
            if row["metric"] in data:
                raise ValueError(f"Duplicate metric: {row['metric']}")
            data[row["metric"]] = {
                k: row[k] for k in ("value", "unit", "currency", "source", "as_of")
            }
        return Financials(ticker=ticker, sector=rows[0]["sector"], data=data)
