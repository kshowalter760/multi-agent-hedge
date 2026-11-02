import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from conftest import approve_chain, build

from workstation.config import Config
from workstation.store import GateError, Store, now


def test_end_to_end(ws, chain):
    analyst, risk, pm = chain
    assert [agent for agent, _ in ws.provider.calls] == ["analyst", "risk", "pm"]
    assert "independent_checks" in ws.provider.calls[1][1]
    with pytest.raises(ValueError, match="approval"):
        ws.store.execute(pm)
    approve_chain(ws, chain)
    ws.store.execute(pm)
    status = ws.store.status()
    assert len(status["ledger"]) == 1
    assert status["portfolio"]["cash"] == 95000
    assert status["portfolio"]["positions"][0]["shares"] == 50
    assert ws.store.get(pm)["status"] == "executed"
    assert "not financial advice" in (ws.store.root / "proposals" / f"{analyst}.md").read_text()
    assert ws.store.get(risk)["payload"]["research"]["risk_checks"]["recomputed"]["fair_value"] > 0


def test_idempotent_and_concurrent_execution(ws, chain):
    approve_chain(ws, chain)

    def execute(_):
        try:
            Store(ws.store.root, ws.config).execute(chain[-1])
            return "executed"
        except ValueError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(execute, range(2))) == ["blocked", "executed"]
    assert len(ws.store.status()["ledger"]) == 1


@pytest.mark.parametrize("target", [0, 1, 2])
def test_hash_tampering_revokes_chain(ws, chain, target):
    approve_chain(ws, chain)
    path = ws.store.root / "proposals" / f"{chain[target]}.md"
    path.write_text(path.read_text() + "\nUnauthorized edit", encoding="utf-8")
    with pytest.raises(GateError, match="hash changed"):
        ws.store.execute(chain[-1])
    with ws.store.transaction() as db:
        row = ws.store.row(db, chain[target])
        assert row["approval_hash"] is None
        assert row["status"] == "changes_requested"
        assert (
            db.execute("SELECT count(*) FROM audit WHERE event='content_invalidated'").fetchone()[0]
            == 1
        )
    with pytest.raises(GateError):
        ws.store.decide(chain[target], "approved")
    assert ws.store.status()["ledger"] == []


def test_halt_persists(ws, chain):
    approve_chain(ws, chain)
    ws.store.halt("manual stop")
    reloaded = Store(ws.store.root, ws.config)
    with pytest.raises(ValueError, match="kill switch"):
        reloaded.execute(chain[-1])
    assert reloaded.status()["halted"]


def test_state_machine_and_rejection(ws, chain):
    with pytest.raises(ValueError, match="Invalid transition"):
        with ws.store.transaction() as db:
            ws.store.transition(db, chain[0], "executed", "human")
    ws.store.decide(chain[0], "rejected", reason="Unsupported forecast")
    with pytest.raises(ValueError, match="Invalid transition"):
        ws.store.decide(chain[0], "approved")
    with pytest.raises(ValueError, match="active analyst"):
        asyncio.run(ws.review(chain[0]))


def test_changes_requested_needs_new_proposal(ws, chain):
    ws.store.decide(chain[0], "changes_requested", reason="Rework margin")
    with pytest.raises(ValueError, match="Invalid transition"):
        ws.store.decide(chain[0], "approved")


def test_self_approval_and_senior_default(ws, chain):
    with pytest.raises(ValueError, match="Only human"):
        ws.store.decide(chain[0], "approved", actor="analyst")
    with pytest.raises(ValueError, match="disabled"):
        ws.store.decide(
            chain[0], "approved", actor="senior", expected_hash=ws.store.get(chain[0])["hash"]
        )
    ws.config.senior_approval_enabled = True
    report = asyncio.run(ws.senior_decide(chain[0]))
    assert ws.store.get(chain[0])["approver"] == "senior"
    with pytest.raises(ValueError, match="Self-approval"):
        ws.store.decide(
            report, "approved", actor="senior", expected_hash=ws.store.get(report)["hash"]
        )


def test_expiry_persists(ws, chain, monkeypatch):
    approve_chain(ws, chain)
    future = now() + timedelta(days=2)
    monkeypatch.setattr("workstation.store.now", lambda: future)
    with pytest.raises(GateError, match="expired"):
        ws.store.execute(chain[-1])
    with ws.store.transaction() as db:
        assert ws.store.row(db, chain[-1])["status"] == "expired"
        assert ws.store.row(db, chain[-1])["approval_hash"] is None


def test_risk_reject_human_only_override(ws):
    original = ws.provider.generate

    async def rejecting(agent, *args):
        output = await original(agent, *args)
        if agent == "risk":
            output.verdict = "reject"
        return output

    ws.provider.generate = rejecting
    chain = asyncio.run(build(ws))
    ws.store.decide(chain[0], "approved")
    with pytest.raises(ValueError, match="only a human"):
        ws.store.decide(chain[1], "approved")
    ws.config.senior_approval_enabled = True
    with pytest.raises(ValueError, match="Only a human"):
        ws.store.decide(chain[1], "approved", actor="senior", override_reason="bypass")
    with pytest.raises(ValueError, match="only a human"):
        asyncio.run(ws.senior_decide(chain[-1]))
    ws.store.decide(
        chain[1], "approved", override_reason="Human accepts stress risk for paper experiment"
    )
    ws.store.decide(chain[2], "approved")
    ws.store.execute(chain[2])
    with ws.store.transaction() as db:
        details = [
            json.loads(r[0])
            for r in db.execute("SELECT details FROM audit WHERE event='in_review->approved'")
        ]
        assert any("Human accepts" in d["risk_override"] for d in details)


def test_append_only_audit_and_ledger(ws, chain):
    approve_chain(ws, chain)
    ws.store.execute(chain[-1])
    for table in ("audit", "ledger"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            with ws.store.transaction() as db:
                db.execute(f"DELETE FROM {table}")


def test_parallel_tickers(ws):
    ws.config.concurrency = 2
    result = asyncio.run(ws.analyze_many(["DEMO", "OTHER", "THIRD"]))
    assert len({r["id"] for r in result}) == 3
    assert len(ws.store.status()["proposals"]) == 3


def test_no_real_execution(ws, chain):
    approve_chain(ws, chain)
    ws.config.DANGEROUS_ENABLE_REAL_EXECUTION = True
    with pytest.raises(ValueError, match="NOT IMPLEMENTED"):
        ws.store.execute(chain[-1])
    assert not ws.store.status()["ledger"]


def test_multiple_orders_recheck_constraints(ws, chain):
    others = [asyncio.run(ws.propose(chain[1])) for _ in range(2)]
    approve_chain(ws, chain)
    for pid in others:
        ws.store.decide(pid, "approved")
    ws.store.execute(chain[-1])
    ws.store.execute(others[0])
    with pytest.raises(ValueError, match="position size"):
        ws.store.execute(others[1])
    assert ws.store.portfolio()["cash"] == 90000


def test_persisted_portfolio_currency(ws):
    other = Store(ws.store.root, Config(currency="EUR"))
    with pytest.raises(ValueError, match="currency"):
        other.portfolio()


def test_policy_change_requires_new_proposal(ws, chain):
    approve_chain(ws, chain)
    ws.config.max_position_size = 0.5
    with pytest.raises(ValueError, match="policy changed"):
        ws.store.execute(chain[-1])


def test_raw_file_status_edit_cannot_approve(ws, chain):
    path = ws.store.root / "proposals" / f"{chain[-1]}.md"
    path.write_text(path.read_text().replace("status: in_review", "status: approved"))
    with pytest.raises(GateError, match="hash changed"):
        ws.store.execute(chain[-1])


def test_stale_input_blocks_before_model_call(ws, monkeypatch):
    monkeypatch.setattr("workstation.workflow.now", lambda: now() + timedelta(days=200))
    with pytest.raises(ValueError, match="stale"):
        asyncio.run(ws.analyze("DEMO"))
    assert not ws.provider.calls


def test_missing_proposal_file_invalidates(ws, chain):
    approve_chain(ws, chain)
    (ws.store.root / "proposals" / f"{chain[-1]}.md").unlink()
    with pytest.raises(GateError, match="hash changed"):
        ws.store.execute(chain[-1])


def test_demo_model_contexts_fit_default(ws, chain):
    from workstation.agents.common import prompt
    from workstation.llm import estimate_tokens
    from workstation.schemas import AnalystOutput, PMOutput, RiskOutput, SeniorOutput

    ws.config.senior_approval_enabled = True
    asyncio.run(ws.senior_decide(chain[-1]))
    schemas = {"analyst": AnalystOutput, "risk": RiskOutput, "pm": PMOutput, "senior": SeniorOutput}
    for agent, payload in ws.provider.calls:
        text = prompt(agent)[0] + json.dumps(payload, ensure_ascii=False)
        text += json.dumps(schemas[agent].model_json_schema())
        assert estimate_tokens(text) + ws.config.max_output_tokens <= ws.config.num_ctx, agent
