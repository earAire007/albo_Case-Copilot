"""Approval ledger (spec 06, invariant 2): the only place that writes decisions and
executions. Protected by import-linter: only backend.executor and backend.approval may
import it; the orchestrator, the worker and the store itself cannot.

`record_execution` re-checks the approval inside the same IMMEDIATE transaction, so an
execution without an approved decision is never inserted, even by a caller that evades
the contract.

Case statuses after the decision (spec 07) are written here, in the same transaction:
a rejection sets `rejected`; an approval sets `execution_failed` (pessimistic: if the
execution raises or the process dies before it, the case never looks approved); the
recorded execution sets `approved`.
"""

import json
import sqlite3
from typing import Any, Literal

from backend.security.masking import mask_text
from backend.store.store import Store, now_iso

Decision = Literal["approved", "rejected"]


class NotApprovedError(PermissionError):
    pass


def record_decision(
    store: Store,
    proposal_id: int,
    *,
    approver: str,
    decision: Decision,
    reply_snapshot: str | None = None,
) -> None:
    """`reply_snapshot` (spec 07) is the reply in force when deciding, masked."""
    if not approver.strip():
        raise ValueError("approver vacío")
    snapshot = None if reply_snapshot is None else mask_text(reply_snapshot)
    with store.lock:
        store.get_proposal(proposal_id)
        try:
            with store.connection:
                store.connection.execute(
                    "INSERT INTO decisions"
                    " (proposal_id, approver, decision, reply_snapshot, decided_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (proposal_id, mask_text(approver.strip()), decision, snapshot, now_iso()),
                )
                status = "rejected" if decision == "rejected" else "execution_failed"
                _set_case_status(store.connection, proposal_id, status)
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "la propuesta ya tiene una decisión, o la decisión no es válida"
            ) from exc


def decision(store: Store, proposal_id: int) -> dict[str, Any] | None:
    with store.lock:
        row = store.connection.execute(
            "SELECT * FROM decisions WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
    return dict(row) if row else None


def executions(store: Store, proposal_id: int) -> list[dict[str, Any]]:
    with store.lock:
        rows = store.connection.execute(
            "SELECT * FROM executions WHERE proposal_id = ?", (proposal_id,)
        ).fetchall()
    return [{**dict(r), "result": json.loads(r["result"])} for r in rows]


def record_execution(store: Store, proposal_id: int, result: dict[str, Any]) -> dict[str, Any]:
    """At most one execution per proposal, and only with an approved decision, both checked
    in the same transaction as the insert."""
    db = store.connection
    with store.lock:
        return _record_execution_locked(db, proposal_id, result)


def _record_execution_locked(
    db: sqlite3.Connection, proposal_id: int, result: dict[str, Any]
) -> dict[str, Any]:
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute(
            "INSERT OR IGNORE INTO executions (proposal_id, result, executed_at)"
            " SELECT ?, ?, ? WHERE EXISTS ("
            "   SELECT 1 FROM decisions WHERE proposal_id = ? AND decision = 'approved')",
            (proposal_id, json.dumps(result, ensure_ascii=False), now_iso(), proposal_id),
        )
        row = db.execute(
            "SELECT result FROM executions WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        if row is not None:
            _set_case_status(db, proposal_id, "approved")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    if row is None:
        raise NotApprovedError("la propuesta no tiene una aprobación registrada")
    stored: dict[str, Any] = json.loads(row["result"])
    return stored


def _set_case_status(db: sqlite3.Connection, proposal_id: int, status: str) -> None:
    """Inside the caller's transaction."""
    db.execute(
        "UPDATE cases SET status = ?, updated_at = ?"
        " WHERE id = (SELECT case_id FROM proposals WHERE id = ?)",
        (status, now_iso(), proposal_id),
    )
