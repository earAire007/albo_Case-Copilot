"""Approval flow (spec 06): the only caller of the executor besides tests, and one of the
two modules allowed to touch the ledger. Never touches the model (import-linter).

States are terminal: a rejected proposal cannot be approved and an approved one cannot be
rejected. Repeating approve on an approved proposal returns the same execution.
"""

from typing import Any

from backend.executor.executor import execute
from backend.store import ledger
from backend.store.store import Store


class ConflictError(Exception):
    """The proposal already has a different, final decision."""


def _check_approver(approver: str) -> str:
    if not approver.strip():
        raise ValueError("approver vacío")
    return approver.strip()


def approve(store: Store, proposal_id: int, approver: str) -> dict[str, Any]:
    approver = _check_approver(approver)
    # Read-check-write under the store lock: concurrent approve/reject cannot interleave.
    with store.lock:
        return _approve_locked(store, proposal_id, approver)


def _approve_locked(store: Store, proposal_id: int, approver: str) -> dict[str, Any]:
    store.get_proposal(proposal_id)
    current = ledger.decision(store, proposal_id)
    if current is None:
        try:
            ledger.record_decision(store, proposal_id, approver=approver, decision="approved")
        except ValueError as exc:  # a concurrent decision won the race
            raise ConflictError("la propuesta ya tiene una decisión") from exc
    elif current["decision"] != "approved":
        raise ConflictError("una propuesta rechazada no puede aprobarse")
    return execute(store, proposal_id)


def reject(store: Store, proposal_id: int, approver: str, reason: str) -> dict[str, Any]:
    approver = _check_approver(approver)
    with store.lock:
        return _reject_locked(store, proposal_id, approver, reason)


def _reject_locked(store: Store, proposal_id: int, approver: str, reason: str) -> dict[str, Any]:
    proposal = store.get_proposal(proposal_id)
    if ledger.decision(store, proposal_id) is not None:
        raise ConflictError("la propuesta ya tiene una decisión")
    try:
        ledger.record_decision(store, proposal_id, approver=approver, decision="rejected")
    except ValueError as exc:
        raise ConflictError("la propuesta ya tiene una decisión") from exc
    store.add_trace(proposal["case_id"], "rejected_by_ops", {"reason": reason})
    decision = ledger.decision(store, proposal_id)
    assert decision is not None
    return decision


def decision_of(store: Store, proposal_id: int) -> dict[str, Any] | None:
    return ledger.decision(store, proposal_id)
