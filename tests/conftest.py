import asyncio
import socket
from datetime import date
from pathlib import Path

import pytest

from workstation.config import Config
from workstation.data import CSVProvider
from workstation.llm import MockProvider
from workstation.schemas import Financials
from workstation.store import Store
from workstation.workflow import Workstation


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    # Block outbound connections, while allowing Windows asyncio's internal socketpair.
    original = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
            raise AssertionError(f"Unexpected outbound network: {address}")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)

    def no_dns(*args, **kwargs):
        raise AssertionError("Tests must not resolve network hosts")

    monkeypatch.setattr(socket, "getaddrinfo", no_dns)


@pytest.fixture
def financials():
    f = CSVProvider(Path(__file__).parents[1] / "examples" / "financials.csv").fetch("DEMO")
    raw = f.model_dump(mode="json")
    for item in raw["data"].values():
        item["as_of"] = date.today().isoformat()
    return Financials.model_validate(raw)


class FixtureData:
    def __init__(self, f):
        self.f = f

    def fetch(self, ticker):
        return self.f.model_copy(update={"ticker": ticker})


@pytest.fixture
def ws(tmp_path, financials):
    config = Config()
    return Workstation(
        config, Store(tmp_path, config), MockProvider(config), FixtureData(financials)
    )


async def build(ws):
    await ws.provider.health()
    analyst = await ws.analyze("DEMO")
    risk = await ws.review(analyst)
    pm = await ws.propose(risk)
    return analyst, risk, pm


@pytest.fixture
def chain(ws):
    return asyncio.run(build(ws))


def approve_chain(ws, chain):
    for pid in chain:
        ws.store.decide(pid, "approved")
