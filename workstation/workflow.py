import asyncio
import json

from .agents import analyst, pm, risk
from .agents.common import prompt
from .config import Config
from .data import DataProvider
from .executor import check_trade, plan_trade
from .llm import LLMProvider
from .provenance import render_narrative
from .schemas import Assumptions, Financials, SeniorOutput
from .store import Store, now


class Workstation:
    def __init__(self, config: Config, store: Store, provider: LLMProvider, data: DataProvider):
        self.config, self.store, self.provider, self.data = config, store, provider, data

    def stage(self, agent, research, memo, version, action, parents=None):
        model = getattr(self.config, agent).model
        return self.store.create(
            ticker=research["financials"]["ticker"],
            agent=agent,
            model=model,
            digest=self.provider.digests[model],
            prompt_version=version,
            research=research,
            memo=memo,
            requested_action=action,
            parents=parents,
        )

    async def analyze(self, ticker):
        f = self.data.fetch(ticker.upper())
        if any(
            (now().date() - d.as_of).days > self.config.max_data_age_days for d in f.data.values()
        ):
            raise ValueError("Input financials are stale; supply newer sourced data")
        output, calc, memo, version = await analyst.run(self.provider, f, self.config)
        research = {
            "financials": f.model_dump(mode="json"),
            "assumptions": output.assumptions.model_dump(),
            "calc": calc,
        }
        return self.stage(
            "analyst",
            research,
            "# Equity research\n\n" + memo,
            version,
            {"action": "publish_research"},
        )

    async def analyze_many(self, tickers):
        # Bound whole research jobs as well as model calls to avoid an unbounded queue.
        semaphore = asyncio.Semaphore(self.config.concurrency)

        async def bounded(ticker):
            async with semaphore:
                try:
                    return {"ticker": ticker, "id": await self.analyze(ticker)}
                except (ValueError, OSError) as exc:
                    return {"ticker": ticker, "error": str(exc)}

        async with asyncio.timeout(self.config.wall_clock_seconds):
            return await asyncio.gather(*(bounded(t) for t in tickers))

    async def review(self, analyst_id):
        parent = self.store.get(analyst_id)
        payload = parent["payload"]
        if payload["author_agent"] != "analyst" or parent["status"] not in {
            "in_review",
            "approved",
        }:
            raise ValueError("Review requires an active analyst proposal")
        research = payload["research"]
        f = Financials.model_validate(research["financials"])
        a = Assumptions.model_validate(research["assumptions"])
        output, checks, memo, version = await risk.run(
            self.provider, f, a, research["calc"], payload["memo"], self.config
        )
        research = research | {"risk_checks": checks, "risk_output": output.model_dump()}
        return self.stage(
            "risk",
            research,
            "# Adversarial risk review\n\n" + memo,
            version,
            {"verdict": output.verdict},
            {analyst_id: parent["hash"]},
        )

    async def propose(self, risk_id):
        parent = self.store.get(risk_id)
        payload = parent["payload"]
        if payload["author_agent"] != "risk" or parent["status"] not in {"in_review", "approved"}:
            raise ValueError("Propose requires an active risk review ID")
        analyst_id = next(iter(payload["parents"]))
        analyst_proposal = self.store.get(analyst_id)
        research = payload["research"]
        f = Financials.model_validate(research["financials"])
        a = Assumptions.model_validate(research["assumptions"])
        portfolio = self.store.portfolio()
        output, memo, version = await pm.run(
            self.provider,
            f,
            a,
            research["calc"],
            analyst_proposal["payload"]["memo"],
            payload["memo"],
            portfolio,
            self.config,
        )
        trade = plan_trade(output.model_dump(), research["financials"], portfolio)
        check_trade(trade, portfolio, self.config)
        action = output.model_dump(exclude={"narrative"}) | {"trade": trade}
        memo += (
            "\n\nPaper order (source: PM assumptions and deterministic sizing; "
            + f"input as-of {payload['as_of']}).\n\n```json\n{json.dumps(action, indent=2)}\n```"
        )
        research = research | {
            "portfolio_at_proposal": portfolio,
            "execution_policy": {
                k: getattr(self.config, k)
                for k in ("max_position_size", "max_sector_exposure", "cash_floor", "currency")
            },
        }
        return self.stage(
            "pm",
            research,
            "# Portfolio proposal\n\n" + memo,
            version,
            action,
            {risk_id: parent["hash"]},
        )

    async def senior_decide(self, pid):
        if not self.config.senior_approval_enabled:
            raise ValueError("Senior approval is disabled; human approval is the default")
        target = self.store.get(pid)
        p = target["payload"]
        if p["author_agent"] == "senior":
            raise ValueError("Senior self-approval forbidden")
        with self.store.transaction() as db:
            self.store.risk_gate(db, pid)
        system, version = prompt("senior")
        # Include the full review chain, but avoid duplicating large research snapshots.
        dependencies = []
        pending = list(p["parents"])
        seen = set()
        while pending:
            parent_id = pending.pop()
            if parent_id in seen:
                continue
            seen.add(parent_id)
            parent = self.store.get(parent_id)["payload"]
            dependencies.append({k: parent[k] for k in ("id", "author_agent", "memo")})
            pending.extend(parent["parents"])
        summary = {k: p[k] for k in ("id", "author_agent", "memo", "requested_action")}
        evidence = {k: p["research"][k] for k in ("financials", "assumptions", "calc")}
        output = await self.provider.generate(
            "senior",
            system,
            {"proposal": summary, "dependencies": dependencies, "evidence": evidence},
            SeniorOutput,
        )
        r = p["research"]
        memo = render_narrative(
            output.reasons,
            Financials.model_validate(r["financials"]),
            Assumptions.model_validate(r["assumptions"]),
            r["calc"],
        )
        report = self.stage(
            "senior",
            r,
            "# Senior review\n\n" + memo,
            version,
            {"target": pid, "verdict": output.verdict},
            {pid: target["hash"]},
        )
        decision = {
            "approve": "approved",
            "request_changes": "changes_requested",
            "reject": "rejected",
        }[output.verdict]
        self.store.decide(
            pid,
            decision,
            actor="senior",
            reason=f"Staged senior report {report}: {memo}",
            expected_hash=target["hash"],
        )
        return report
