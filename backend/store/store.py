"""Neutral SQLite persistence for application state (spec 05a): proposals, approval
decisions, executions and traces. Never the mock dataset, which stays immutable.

Every free-text column is masked on the way in (trace payloads, proposal justification,
approver): whatever a caller passes, nothing sensitive is persisted.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from backend.security.masking import Json, mask, mask_text

DEFAULT_DB = Path(__file__).resolve().parents[2] / "var" / "copilot.db"
Decision = Literal["approved", "rejected"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    action TEXT NOT NULL,
    txn_id TEXT NOT NULL,
    justification TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    proposal_id INTEGER PRIMARY KEY REFERENCES proposals(id),
    approver TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS executions (
    proposal_id INTEGER PRIMARY KEY REFERENCES proposals(id),
    result TEXT NOT NULL,
    executed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    step TEXT NOT NULL,
    validator TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = DEFAULT_DB) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    # --- proposals and the approval gate ---

    def create_proposal(self, case_id: str, action: str, txn_id: str, justification: str) -> int:
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO proposals (case_id, action, txn_id, justification, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (case_id, action, txn_id, mask_text(justification), _now()),
            )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def get_proposal(self, proposal_id: int) -> dict[str, Any]:
        row = self._db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if row is None:
            raise KeyError(proposal_id)
        return dict(row)

    def record_decision(self, proposal_id: int, *, approver: str, decision: Decision) -> None:
        self.get_proposal(proposal_id)
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO decisions (proposal_id, approver, decision, decided_at)"
                    " VALUES (?, ?, ?, ?)",
                    (proposal_id, mask_text(approver), decision, _now()),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "la propuesta ya tiene una decisión, o la decisión no es válida"
            ) from exc

    def decision(self, proposal_id: int) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT * FROM decisions WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        return dict(row) if row else None

    def record_execution(self, proposal_id: int, result: dict[str, Any]) -> dict[str, Any]:
        """At most one execution per proposal: a repeat returns the stored result."""
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO executions (proposal_id, result, executed_at)"
                " VALUES (?, ?, ?)",
                (proposal_id, json.dumps(result, ensure_ascii=False), _now()),
            )
        return self.executions(proposal_id)[0]["result"]

    def executions(self, proposal_id: int) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM executions WHERE proposal_id = ?", (proposal_id,)
        ).fetchall()
        return [{**dict(r), "result": json.loads(r["result"])} for r in rows]

    # --- traces ---

    def add_trace(
        self, case_id: str, step: str, payload: Json, *, validator: str | None = None
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO traces (case_id, step, validator, payload, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (case_id, step, validator, json.dumps(mask(payload), ensure_ascii=False), _now()),
            )

    def traces(self, case_id: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM traces", ()
        if case_id is not None:
            query, params = query + " WHERE case_id = ?", (case_id,)
        rows = self._db.execute(query + " ORDER BY id", params).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def all_rows(self) -> dict[str, list[dict[str, Any]]]:
        return {
            table: [dict(r) for r in self._db.execute(f"SELECT * FROM {table}").fetchall()]
            for table in ("proposals", "decisions", "executions", "traces")
        }

    def rejection_counts(self) -> dict[str, int]:
        rows = self._db.execute(
            "SELECT validator, COUNT(*) AS n FROM traces WHERE step = 'rejection'"
            " GROUP BY validator"
        ).fetchall()
        return {r["validator"]: r["n"] for r in rows}
