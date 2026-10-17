"""Neutral SQLite persistence for application state: cases, jobs, proposals and traces
(specs 05a and 06). Never the mock dataset, which stays immutable.

Every free-text column is masked on the way in (case message, trace payloads, proposal
justification): whatever a caller passes, nothing sensitive is persisted.

Approval decisions and executions are NOT written here: they live in
`backend.store.ledger`, which only the executor and the approval flow may import.
"""

import functools
import json
import sqlite3
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Concatenate

from backend.security.masking import Json, mask, mask_text

DEFAULT_DB = Path(__file__).resolve().parents[2] / "var" / "copilot.db"
# Decided statuses (spec 07) are assigned only by backend.store.ledger, in the same
# transaction as the decision or the execution, and never overwritten.
DECIDED_STATUSES = frozenset({"approved", "rejected", "execution_failed"})
FINAL_STATUSES = frozenset({"proposal_pending", "answered", "requires_human"}) | DECIDED_STATUSES
_NOT_DECIDED = "status NOT IN ({})".format(", ".join(f"'{x}'" for x in sorted(DECIDED_STATUSES)))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    body_hash TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    message TEXT NOT NULL,
    as_of TEXT NOT NULL,
    status TEXT NOT NULL,
    final_reply TEXT,
    edited_by TEXT,
    edited_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    claimed_at TEXT
);
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    action TEXT NOT NULL,
    txn_id TEXT NOT NULL,
    justification TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    proposal_id INTEGER PRIMARY KEY REFERENCES proposals(id),
    approver TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reply_snapshot TEXT,
    decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS executions (
    proposal_id INTEGER PRIMARY KEY REFERENCES proposals(id),
    result TEXT NOT NULL,
    executed_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS decisions_insert_only_update BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions es solo de insercion'); END;
CREATE TRIGGER IF NOT EXISTS decisions_insert_only_delete BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions es solo de insercion'); END;
CREATE TRIGGER IF NOT EXISTS executions_insert_only_update BEFORE UPDATE ON executions
BEGIN SELECT RAISE(ABORT, 'executions es solo de insercion'); END;
CREATE TRIGGER IF NOT EXISTS executions_insert_only_delete BEFORE DELETE ON executions
BEGIN SELECT RAISE(ABORT, 'executions es solo de insercion'); END;
CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    step TEXT NOT NULL,
    validator TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
# Bump on every schema change: there are no migrations, an outdated database is refused.
# Spec 07: final_reply, edited_by, edited_at and reply_snapshot (1); decided statuses (2).
SCHEMA_VERSION = 2
_TABLES = ("cases", "jobs", "proposals", "decisions", "executions", "traces")


def _locked[**P, R](
    method: Callable[Concatenate["Store", P], R],
) -> Callable[Concatenate["Store", P], R]:
    """Serialize every store operation: one connection is shared by the API thread pool
    and the worker, and SQLite transactions belong to the connection, not the thread."""

    @functools.wraps(method)
    def wrapper(self: "Store", *args: P.args, **kwargs: P.kwargs) -> R:
        with self.lock:
            return method(self, *args, **kwargs)

    return wrapper


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class OutdatedSchemaError(RuntimeError):
    pass


def _check_schema_version(db: sqlite3.Connection) -> None:
    version = db.execute("PRAGMA user_version").fetchone()[0]
    has_tables = db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table'").fetchone()
    if version == SCHEMA_VERSION or (version == 0 and has_tables is None):
        return
    db.close()
    raise OutdatedSchemaError(
        f"esquema desactualizado: borra var/copilot.db (versión {version},"
        f" se esperaba {SCHEMA_VERSION})"
    )


class IdempotencyConflictError(ValueError):
    """Same idempotency key, different body."""


class Store:
    def __init__(self, path: str | Path = DEFAULT_DB) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # One connection shared by the API thread pool and the worker; every operation and
        # every ledger transaction holds `lock` (reentrant). Multi-process is out of scope.
        self.lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        # REPLACE deletes the conflicting row; this makes it fire the insert-only triggers.
        self._db.execute("PRAGMA recursive_triggers = ON")
        _check_schema_version(self._db)
        self._db.executescript(_SCHEMA)
        self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @property
    def connection(self) -> sqlite3.Connection:
        return self._db

    # --- cases and the queue (spec 06) ---

    @_locked
    def create_case(
        self,
        *,
        idempotency_key: str,
        body_hash: str,
        ticket_id: str,
        customer_id: str,
        message: str,
        as_of: datetime,
    ) -> tuple[dict[str, Any], bool]:
        """Idempotent intake: (case, created). Same key + other body -> conflict."""
        existing = self._db.execute(
            "SELECT * FROM cases WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing is not None:
            if existing["body_hash"] != body_hash:
                raise IdempotencyConflictError(idempotency_key)
            return dict(existing), False
        case_id = f"case_{uuid.uuid4().hex[:12]}"
        stamp = now_iso()
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO cases (id, idempotency_key, body_hash, ticket_id, customer_id,"
                    " message, as_of, status, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)",
                    (
                        case_id,
                        idempotency_key,
                        body_hash,
                        ticket_id,
                        customer_id,
                        mask_text(message),
                        as_of.isoformat(),
                        stamp,
                        stamp,
                    ),
                )
                self._db.execute(
                    "INSERT INTO jobs (case_id, status) VALUES (?, 'queued')", (case_id,)
                )
        except sqlite3.IntegrityError:
            # A concurrent retry with the same key won the race.
            return self.create_case(
                idempotency_key=idempotency_key,
                body_hash=body_hash,
                ticket_id=ticket_id,
                customer_id=customer_id,
                message=message,
                as_of=as_of,
            )
        return self.get_case(case_id), True

    @_locked
    def get_case(self, case_id: str) -> dict[str, Any]:
        row = self._db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise KeyError(case_id)
        return dict(row)

    @_locked
    def list_cases(self, status: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM cases", ()
        if status is not None:
            query, params = query + " WHERE status = ?", (status,)
        return [dict(r) for r in self._db.execute(query + " ORDER BY created_at", params)]

    @_locked
    def set_case_status(self, case_id: str, status: str) -> None:
        """Worker statuses only. A decided case is never overwritten (a late worker write,
        e.g. racing an approval, is a no-op)."""
        if status in DECIDED_STATUSES:
            raise ValueError("los estados de decisión los asigna solo el ledger")
        with self._db:
            self._db.execute(
                f"UPDATE cases SET status = ?, updated_at = ? WHERE id = ? AND {_NOT_DECIDED}",
                (status, now_iso(), case_id),
            )

    @_locked
    def set_final_reply(self, case_id: str, final_reply: str, *, editor: str) -> None:
        """Human edit of the reply (spec 07). Callers validate first (backend.approval);
        masking here is the backstop, as in every free-text column."""
        stamp = now_iso()
        with self._db:
            cursor = self._db.execute(
                "UPDATE cases SET final_reply = ?, edited_by = ?, edited_at = ?, updated_at = ?"
                " WHERE id = ?",
                (mask_text(final_reply), mask_text(editor), stamp, stamp, case_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(case_id)

    @_locked
    def requeue_stuck_jobs(self, *, older_than: datetime, max_attempts: int) -> int:
        """Stuck jobs go back to the queue, unless they are out of attempts: then the job
        fails and the case goes to a human (no unbounded reprocessing or model cost)."""
        cutoff = older_than.isoformat()
        with self._db:
            exhausted = self._db.execute(
                "SELECT case_id FROM jobs WHERE status = 'running' AND claimed_at < ?"
                " AND attempts >= ?",
                (cutoff, max_attempts),
            ).fetchall()
            for row in exhausted:
                self._db.execute(
                    "UPDATE jobs SET status = 'failed' WHERE case_id = ?", (row["case_id"],)
                )
                self._db.execute(
                    "UPDATE cases SET status = 'requires_human', updated_at = ?"
                    f" WHERE id = ? AND {_NOT_DECIDED}",
                    (now_iso(), row["case_id"]),
                )
            cursor = self._db.execute(
                "UPDATE jobs SET status = 'queued' WHERE status = 'running' AND claimed_at < ?",
                (cutoff,),
            )
        return cursor.rowcount

    @_locked
    def claim_job(self, *, now: datetime) -> dict[str, Any] | None:
        """Atomically take the oldest queued job."""
        with self._db:
            row = self._db.execute(
                "UPDATE jobs SET status = 'running', attempts = attempts + 1, claimed_at = ?"
                " WHERE id = (SELECT id FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1)"
                " RETURNING id, case_id, attempts",
                (now.isoformat(),),
            ).fetchone()
        return dict(row) if row else None

    @_locked
    def finish_job(self, job_id: int, status: str) -> None:
        with self._db:
            self._db.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))

    # --- proposals (decisions and executions: see backend.store.ledger) ---

    @_locked
    def create_proposal(
        self, case_id: str, action: str, txn_id: str, justification: str, *, customer_id: str
    ) -> int:
        """One proposal per case (UNIQUE): a queue retry never duplicates it."""
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO proposals (case_id, customer_id, action, txn_id, justification,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (case_id, customer_id, action, txn_id, mask_text(justification), now_iso()),
            )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    @_locked
    def get_proposal(self, proposal_id: int) -> dict[str, Any]:
        row = self._db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if row is None:
            raise KeyError(proposal_id)
        return dict(row)

    @_locked
    def proposal_for_case(self, case_id: str) -> dict[str, Any] | None:
        row = self._db.execute("SELECT * FROM proposals WHERE case_id = ?", (case_id,)).fetchone()
        return dict(row) if row else None

    # --- traces ---

    @_locked
    def add_trace(
        self, case_id: str, step: str, payload: Json, *, validator: str | None = None
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO traces (case_id, step, validator, payload, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    case_id,
                    step,
                    validator,
                    json.dumps(mask(payload), ensure_ascii=False),
                    now_iso(),
                ),
            )

    @_locked
    def traces(self, case_id: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM traces", ()
        if case_id is not None:
            query, params = query + " WHERE case_id = ?", (case_id,)
        rows = self._db.execute(query + " ORDER BY id", params).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    @_locked
    def all_rows(self) -> dict[str, list[dict[str, Any]]]:
        return {
            table: [dict(r) for r in self._db.execute(f"SELECT * FROM {table}").fetchall()]
            for table in _TABLES
        }

    @_locked
    def rejection_counts(self) -> dict[str, int]:
        rows = self._db.execute(
            "SELECT validator, COUNT(*) AS n FROM traces WHERE step = 'rejection'"
            " GROUP BY validator"
        ).fetchall()
        return {r["validator"]: r["n"] for r in rows}
