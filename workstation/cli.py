import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import httpx

from .config import Config
from .data import CSVProvider
from .llm import MockProvider, OllamaProvider
from .store import Store
from .workflow import Workstation


def parser():
    p = argparse.ArgumentParser(
        prog="ws", description="Approval-gated local research; paper trading only"
    )
    p.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace directory")
    p.add_argument("--config", type=Path, help="TOML configuration (default: ROOT/ws.toml)")
    p.add_argument(
        "--mock", action="store_true", help="Deterministic offline demo; no Ollama calls"
    )
    commands = p.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="Stage analyst research for one or more tickers")
    analyze.add_argument("tickers", nargs="+")
    for command in ("review", "propose", "execute", "show"):
        sub = commands.add_parser(command)
        sub.add_argument("id")
    approve = commands.add_parser("approve")
    approve.add_argument("id")
    approve.add_argument(
        "--senior", action="store_true", help="Explicitly enabled senior-agent review"
    )
    approve.add_argument(
        "--override-risk",
        default="",
        metavar="REASON",
        help="Human-only risk override, recorded in audit",
    )
    reject = commands.add_parser("reject")
    reject.add_argument("id")
    reject.add_argument("--reason", required=True)
    reject.add_argument("--request-changes", action="store_true")
    halt = commands.add_parser("halt")
    halt.add_argument("--reason", default="Operator activated global kill switch")
    commands.add_parser("status")
    commands.add_parser("audit")
    commands.add_parser("doctor", help="Check Ollama and all configured local models")
    return p


async def model_command(args, config, store):
    provider = MockProvider(config) if args.mock else OllamaProvider(config)
    async with asyncio.timeout(config.wall_clock_seconds):
        await provider.health()
        data_path = Path(config.data_file)
        if not data_path.is_absolute():
            data_path = args.root / data_path
        ws = Workstation(config, store, provider, CSVProvider(data_path))
        if args.command == "doctor":
            return {"models": provider.digests}
        if args.command == "analyze":
            return await ws.analyze_many(args.tickers)
        if args.command == "review":
            return {"id": await ws.review(args.id)}
        if args.command == "propose":
            return {"id": await ws.propose(args.id)}
        if args.override_risk:
            raise ValueError("Senior approval cannot override risk")
        return {"senior_report": await ws.senior_decide(args.id)}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        config = Config.load(args.config or args.root / "ws.toml")
        store = Store(args.root, config)
        if args.command in {"analyze", "review", "propose", "doctor"} or (
            args.command == "approve" and args.senior
        ):
            result = asyncio.run(model_command(args, config, store))
        elif args.command == "approve":
            store.decide(args.id, "approved", override_reason=args.override_risk)
            result = {"id": args.id, "status": "approved"}
        elif args.command == "reject":
            decision = "changes_requested" if args.request_changes else "rejected"
            store.decide(args.id, decision, reason=args.reason)
            result = {"id": args.id, "status": decision}
        elif args.command == "execute":
            store.execute(args.id)
            result = {"id": args.id, "status": "executed", "mode": "paper"}
        elif args.command == "halt":
            store.halt(args.reason)
            result = {"halted": True}
        elif args.command == "show":
            store.get(args.id)
            print((args.root / "proposals" / f"{args.id}.md").read_text("utf-8"))
            return
        elif args.command == "audit":
            with store.transaction() as db:
                result = [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY seq")]
        else:
            result = store.status()
        print(json.dumps(result, indent=2))
        if isinstance(result, list) and any("error" in row for row in result):
            raise SystemExit(1)
    except (ValueError, OSError, httpx.HTTPError, TimeoutError, sqlite3.Error) as exc:
        print(f"ws: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
