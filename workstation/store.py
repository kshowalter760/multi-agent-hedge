"""SQLite authority with Markdown review artifacts; fail closed on disk edits.

All lifecycle/portfolio writes serialize using BEGIN IMMEDIATE. Files are replaced
atomically while holding that lock. A crash between DB and file writes fails closed.
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .config import Config
from .data import content_hash
from .executor import PaperExecutor
from .provenance import DISCLAIMER

TRANSITIONS = {
    "draft": {"in_review", "expired"},
    "in_review": {"approved", "changes_requested", "rejected", "expired"},
    "approved": {"executed", "expired", "changes_requested", "rejected"},
    "changes_requested": {"expired"},
    "rejected": {"expired"},
    "executed": set(),
    "expired": set(),
}


def now():
    return datetime.now(timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


class GateError(ValueError):
    """A persisted safety event (invalidation/expiry) must survive the refusal."""


class Store:
    def __init__(self, root: Path, config: Config):
        self.root, self.config = root, config
        (root / ".ws").mkdir(parents=True, exist_ok=True)
        (root / "proposals").mkdir(parents=True, exist_ok=True)
        self.db = root / ".ws" / "workstation.sqlite3"
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, hash TEXT NOT NULL,
                    status TEXT NOT NULL, file_hash TEXT NOT NULL DEFAULT '',
                    approval_hash TEXT, approver TEXT, override_reason TEXT,
                    tainted INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                    proposal_id TEXT, actor TEXT NOT NULL, event TEXT NOT NULL,
                    hash TEXT NOT NULL, details TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
                    BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
                CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
                    BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
                CREATE TABLE IF NOT EXISTS ledger (
                    proposal_id TEXT PRIMARY KEY REFERENCES proposals(id), trade TEXT NOT NULL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
                    BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END;
                CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
                    BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END;
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS positions (
                    ticker TEXT PRIMARY KEY, shares INTEGER NOT NULL,
                    price REAL NOT NULL, sector TEXT NOT NULL
                );
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES ('halted', 'false')")
            db.execute(
                "INSERT OR IGNORE INTO settings VALUES ('cash', ?)", (str(config.initial_cash),)
            )
            db.execute("INSERT OR IGNORE INTO settings VALUES ('currency', ?)", (config.currency,))

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.db, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.commit()
        except GateError:
            db.commit()
            raise
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def audit(self, db, pid, actor, event, digest, details=""):
        db.execute(
            "INSERT INTO audit(timestamp,proposal_id,actor,event,hash,details) "
            "VALUES (?,?,?,?,?,?)",
            (now().isoformat(), pid, actor, event, digest, details),
        )

    def row(self, db, pid):
        row = db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        if not row:
            raise ValueError(f"Unknown proposal: {pid}")
        return row

    def write_file(self, db, pid):
        row = self.row(db, pid)
        payload = json.loads(row["payload"])
        meta = {k: v for k, v in payload.items() if k not in {"memo", "research"}}
        meta |= {
            "status": row["status"],
            "content_hash": row["hash"],
            "approval_hash": row["approval_hash"],
            "approver": row["approver"],
            "override_reason": row["override_reason"],
        }
        text = (
            "---\n"
            + yaml.safe_dump(meta, sort_keys=False)
            + "---\n\n"
            + payload["memo"]
            + "\n\n---\n"
            + DISCLAIMER
            + "\n"
        )
        path = self.root / "proposals" / f"{pid}.md"
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(text.encode("utf-8"))
        os.replace(temporary, path)
        db.execute("UPDATE proposals SET file_hash=? WHERE id=?", (content_hash(text), pid))

    def transition(self, db, pid, target, actor, details=""):
        row = self.row(db, pid)
        if target not in TRANSITIONS[row["status"]]:
            raise ValueError(f"Invalid transition: {row['status']} -> {target}")
        db.execute("UPDATE proposals SET status=? WHERE id=?", (target, pid))
        self.audit(db, pid, actor, f"{row['status']}->{target}", row["hash"], details)
        self.write_file(db, pid)

    def guard(self, db, pid, seen=None):
        seen = set() if seen is None else seen
        if pid in seen:
            raise ValueError("Cyclic proposal dependencies")
        seen.add(pid)
        row = self.row(db, pid)
        if row["tainted"]:
            raise GateError(f"{pid}: content changed; create a new proposal")
        path = self.root / "proposals" / f"{pid}.md"
        observed = content_hash(path.read_bytes()) if path.exists() else "missing"
        if observed != row["file_hash"] or content_hash(row["payload"]) != row["hash"]:
            # Preserve the edited file for inspection; never silently overwrite it.
            target = "changes_requested" if row["status"] == "approved" else row["status"]
            db.execute(
                "UPDATE proposals SET tainted=1,status=?,approval_hash=NULL,approver=NULL,"
                "override_reason=NULL WHERE id=?",
                (target, pid),
            )
            self.audit(
                db,
                pid,
                "system",
                "content_invalidated",
                observed,
                f"{row['status']}->{target}; approval revoked; previous content {row['hash']}",
            )
            raise GateError(
                f"{pid}: content hash changed; approval invalidated; create a new proposal"
            )
        payload = json.loads(row["payload"])
        if row["status"] == "expired":
            raise GateError(f"{pid}: expired")
        dates = [
            datetime.fromisoformat(v["as_of"]).date()
            for v in payload["research"]["financials"]["data"].values()
        ]
        stale = any((now().date() - d).days > self.config.max_data_age_days for d in dates)
        if row["status"] != "executed" and (
            now() >= datetime.fromisoformat(payload["expires_at"]) or stale
        ):
            self.transition(db, pid, "expired", "system", "Proposal TTL or input freshness limit")
            db.execute("UPDATE proposals SET approval_hash=NULL WHERE id=?", (pid,))
            self.write_file(db, pid)
            raise GateError(f"{pid}: expired or stale input data")
        for parent, expected in payload["parents"].items():
            ancestor = self.guard(db, parent, seen.copy())
            if ancestor["hash"] != expected:
                raise GateError("Dependency content changed")
        return row

    def create(
        self,
        *,
        ticker,
        agent,
        model,
        digest,
        prompt_version,
        research,
        memo,
        requested_action,
        parents=None,
    ):
        pid = uuid.uuid4().hex[:16]
        payload = {
            "id": pid,
            "ticker": ticker,
            "author_agent": agent,
            "as_of": min(d["as_of"] for d in research["financials"]["data"].values()),
            "created_at": now().isoformat(),
            "expires_at": (now() + timedelta(hours=self.config.expiry_hours)).isoformat(),
            "input_data_hash": content_hash(canonical(research["financials"])),
            "model_name": model,
            "model_digest": digest,
            "prompt_versions": {agent: prompt_version},
            "generation_options": {
                k: getattr(self.config, k) for k in ("num_ctx", "seed", "temperature")
            },
            "requested_action": requested_action,
            "parents": parents or {},
            "research": research,
            "memo": memo,
        }
        with self.transaction() as db:
            for parent, expected in payload["parents"].items():
                if self.guard(db, parent)["hash"] != expected:
                    raise GateError("Parent changed during generation")
            encoded = canonical(payload)
            digest = content_hash(encoded)
            db.execute(
                "INSERT INTO proposals(id,payload,hash,status) VALUES (?,?,?,'draft')",
                (pid, encoded, digest),
            )
            self.audit(db, pid, agent, "created->draft", digest)
            self.write_file(db, pid)
            self.transition(db, pid, "in_review", agent)
        return pid

    def get(self, pid):
        with self.transaction() as db:
            row = self.guard(db, pid)
            return dict(row) | {"payload": json.loads(row["payload"])}

    def risk_gate(self, db, pid, override=False):
        row = self.guard(db, pid)
        payload = json.loads(row["payload"])
        if payload["author_agent"] == "risk":
            verdict = payload["requested_action"]["verdict"]
            if (
                verdict in {"reject", "request_changes"}
                and not row["override_reason"]
                and not override
            ):
                raise ValueError(f"Risk {verdict}: only a human can override with a reason")
        for parent in payload["parents"]:
            self.risk_gate(db, parent, override)

    def decide(
        self, pid, decision, *, actor="human", reason="", override_reason="", expected_hash=None
    ):
        if actor not in {"human", "senior"}:
            raise ValueError("Only human or explicitly enabled senior decisions are accepted")
        if actor != "human" and override_reason:
            raise ValueError("Only a human can override risk")
        with self.transaction() as db:
            row = self.guard(db, pid)
            payload = json.loads(row["payload"])
            if actor == payload["author_agent"]:
                raise ValueError("Self-approval forbidden")
            if actor == "senior" and not self.config.senior_approval_enabled:
                raise ValueError("Senior approval is disabled")
            if actor == "senior" and not expected_hash:
                raise ValueError("Senior review must be bound to the reviewed hash")
            if expected_hash and expected_hash != row["hash"]:
                raise ValueError("Reviewed hash no longer matches")
            if decision == "approved":
                self.risk_gate(db, pid, bool(override_reason.strip()))
                db.execute(
                    "UPDATE proposals SET approval_hash=?,approver=?,override_reason=? WHERE id=?",
                    (row["hash"], actor, override_reason.strip() or None, pid),
                )
            elif decision in {"rejected", "changes_requested"}:
                if not reason.strip():
                    raise ValueError("A decision reason is required")
                db.execute(
                    "UPDATE proposals SET approval_hash=NULL,approver=NULL,"
                    "override_reason=NULL WHERE id=?",
                    (pid,),
                )
            else:
                raise ValueError("Unsupported approval decision")
            self.transition(
                db,
                pid,
                decision,
                actor,
                canonical({"reason": reason, "risk_override": override_reason}),
            )

    def portfolio(self, db=None):
        if db is None:
            with self.transaction() as connection:
                return self.portfolio(connection)
        currency = db.execute("SELECT value FROM settings WHERE key='currency'").fetchone()[0]
        if currency != self.config.currency:
            raise ValueError("Configured currency differs from existing ledger")
        return {
            "cash": float(db.execute("SELECT value FROM settings WHERE key='cash'").fetchone()[0]),
            "currency": currency,
            "positions": [dict(r) for r in db.execute("SELECT * FROM positions ORDER BY ticker")],
        }

    def approved_chain(self, db, pid):
        row = self.guard(db, pid)
        if row["status"] != "approved" or row["approval_hash"] != row["hash"]:
            raise ValueError(f"{pid}: every dependency needs current hash-bound approval")
        for parent in json.loads(row["payload"])["parents"]:
            self.approved_chain(db, parent)

    def execute(self, pid):
        with self.transaction() as db:
            if db.execute("SELECT value FROM settings WHERE key='halted'").fetchone()[0] == "true":
                raise ValueError("Global kill switch is active")
            if db.execute("SELECT 1 FROM ledger WHERE proposal_id=?", (pid,)).fetchone():
                raise ValueError("Proposal already executed; duplicate execution forbidden")
            row = self.guard(db, pid)
            payload = json.loads(row["payload"])
            if payload["author_agent"] != "pm":
                raise ValueError("Only PM proposals can produce ledger entries")
            policy = payload["research"]["execution_policy"]
            if any(getattr(self.config, key) != value for key, value in policy.items()):
                raise ValueError("Execution policy changed; create and approve a new PM proposal")
            self.approved_chain(db, pid)
            self.risk_gate(db, pid, bool(row["override_reason"] and row["approver"] == "human"))
            PaperExecutor().execute(
                db, pid, payload["requested_action"]["trade"], self.portfolio(db), self.config
            )
            self.transition(db, pid, "executed", "paper_executor")

    def halt(self, reason):
        with self.transaction() as db:
            db.execute("UPDATE settings SET value='true' WHERE key='halted'")
            self.audit(db, None, "human", "halted", content_hash(reason), reason)

    def status(self):
        with self.transaction() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM proposals")]
            for pid in ids:
                try:
                    self.guard(db, pid)
                except GateError:
                    pass
            rows = []
            for row in db.execute("SELECT * FROM proposals ORDER BY rowid"):
                payload = json.loads(row["payload"])
                rows.append(
                    {
                        "id": row["id"],
                        "ticker": payload["ticker"],
                        "agent": payload["author_agent"],
                        "status": row["status"],
                        "tainted": bool(row["tainted"]),
                        "hash": row["hash"],
                    }
                )
            return {
                "halted": db.execute("SELECT value FROM settings WHERE key='halted'").fetchone()[0]
                == "true",
                "proposals": rows,
                "portfolio": self.portfolio(db),
                "ledger": [dict(r) for r in db.execute("SELECT * FROM ledger")],
            }
