import math
from abc import ABC, abstractmethod

from .config import Config


def plan_trade(output: dict, financials: dict, portfolio: dict) -> dict:
    price = financials["data"]["price"]["value"]
    nav = portfolio["cash"] + sum(p["shares"] * p["price"] for p in portfolio["positions"])
    action = output["action"]
    if action == "hold" and output["weight"] != 0:
        raise ValueError("Hold must have zero trade weight")
    shares = 0 if action == "hold" else math.floor(output["weight"] * nav / price)
    if action != "hold" and shares <= 0:
        raise ValueError("Trade rounds to zero shares")
    return {
        "action": action,
        "shares": shares,
        "price": price,
        "limit_price": output["limit_price"],
        "ticker": financials["ticker"],
        "sector": financials["sector"],
        "currency": financials["data"]["price"]["currency"],
    }


def check_trade(trade: dict, portfolio: dict, config: Config) -> tuple[float, dict]:
    if trade["currency"] != config.currency:
        raise ValueError("Trade currency differs from portfolio currency")
    positions = {p["ticker"]: dict(p) for p in portfolio["positions"]}
    existing = positions.get(
        trade["ticker"],
        {
            "ticker": trade["ticker"],
            "shares": 0,
            "price": trade["price"],
            "sector": trade["sector"],
        },
    )
    if existing["sector"] != trade["sector"]:
        raise ValueError("Sector changed; reconcile portfolio manually")
    cash = portfolio["cash"]
    action, shares, price = trade["action"], trade["shares"], trade["price"]
    if action == "hold":
        return cash, positions
    if shares <= 0 or price <= 0:
        raise ValueError("Invalid paper order")
    if action == "buy":
        if price > trade["limit_price"]:
            raise ValueError("Buy limit not met")
        existing["shares"] += shares
        cash -= shares * price
    elif action == "sell":
        if price < trade["limit_price"]:
            raise ValueError("Sell limit not met")
        existing["shares"] -= shares
        cash += shares * price
        if existing["shares"] < 0:
            raise ValueError("Short selling is disabled")
    else:
        raise ValueError("Unknown trade action")
    existing["price"] = price
    positions[trade["ticker"]] = existing
    nav = cash + sum(p["shares"] * p["price"] for p in positions.values())
    if nav <= 0 or cash < config.cash_floor * nav - 1e-8:
        raise ValueError("Cash floor violated")
    sectors = {}
    for p in positions.values():
        value = p["shares"] * p["price"]
        if value > config.max_position_size * nav + 1e-8:
            raise ValueError("Max position size violated")
        sectors[p["sector"]] = sectors.get(p["sector"], 0) + value
    if any(value > config.max_sector_exposure * nav + 1e-8 for value in sectors.values()):
        raise ValueError("Max sector exposure violated")
    return cash, positions


class Executor(ABC):
    @abstractmethod
    def execute(self, connection, proposal_id: str, trade: dict, portfolio: dict, config: Config):
        """Must run inside the proposal store's approval-checked transaction."""


class PaperExecutor(Executor):
    def execute(self, connection, proposal_id, trade, portfolio, config):
        if config.DANGEROUS_ENABLE_REAL_EXECUTION:
            raise ValueError(
                "REAL EXECUTION IS NOT IMPLEMENTED; disable DANGEROUS_ENABLE_REAL_EXECUTION"
            )
        cash, positions = check_trade(trade, portfolio, config)
        connection.execute("UPDATE settings SET value=? WHERE key='cash'", (str(cash),))
        for p in positions.values():
            connection.execute(
                "INSERT OR REPLACE INTO positions VALUES (?,?,?,?)",
                (p["ticker"], p["shares"], p["price"], p["sector"]),
            )
        import json

        connection.execute(
            "INSERT INTO ledger(proposal_id,trade) VALUES (?,?)",
            (proposal_id, json.dumps(trade, sort_keys=True)),
        )
