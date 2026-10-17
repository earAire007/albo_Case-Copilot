"""Spec 05a — gate de aprobación y executor (idempotente, sin mover dinero)."""

import pytest

from backend.executor.executor import NotApprovedError, execute
from backend.store import ledger
from backend.store.store import Store


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def _proposal(store: Store) -> int:
    return store.create_proposal(
        "case_1", "open_dispute", "txn_0165", "cargo duplicado", customer_id="cus_004"
    )


def test_executor_requires_recorded_approval(store):
    pid = _proposal(store)
    with pytest.raises(NotApprovedError):
        execute(store, pid)
    assert ledger.executions(store, pid) == []
    ledger.record_decision(store, pid, approver="ops@empresa", decision="approved")
    result = execute(store, pid)
    assert result["action"] == "open_dispute" and result["txn_id"] == "txn_0165"
    approval = ledger.decision(store, pid)
    assert approval is not None and approval["approver"] == "ops@empresa"
    assert approval["decided_at"]


def test_execution_is_idempotent(store):
    pid = _proposal(store)
    ledger.record_decision(store, pid, approver="ops", decision="approved")
    first = execute(store, pid)
    second = execute(store, pid)
    assert first == second
    assert len(ledger.executions(store, pid)) == 1


def test_rejected_proposal_cannot_execute(store):
    pid = _proposal(store)
    ledger.record_decision(store, pid, approver="ops", decision="rejected")
    with pytest.raises(NotApprovedError):
        execute(store, pid)
    assert ledger.executions(store, pid) == []


def test_decision_is_final(store):
    pid = _proposal(store)
    ledger.record_decision(store, pid, approver="ops", decision="rejected")
    with pytest.raises(ValueError):
        ledger.record_decision(store, pid, approver="otro", decision="approved")


def test_unknown_action_is_never_executed(store):
    pid = store.create_proposal("case_1", "refund", "txn_0165", "inyectado", customer_id="cus_004")
    ledger.record_decision(store, pid, approver="ops", decision="approved")
    with pytest.raises(ValueError):
        execute(store, pid)
    assert ledger.executions(store, pid) == []
