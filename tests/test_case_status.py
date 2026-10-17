"""Spec 07 (ajuste) — estados de caso tras la decisión: approved, rejected y
execution_failed, asignados por el ledger en la misma transacción que la decisión o la
ejecución, terminales para la decisión."""

import pytest

from backend.approval import service
from backend.store import ledger
from backend.store.store import Store

from .spec06_helpers import case_with_proposal, client_for, post_ticket, work
from .test_loop import FakeModel


def _status(client, case_id):
    return client.get(f"/cases/{case_id}").json()["status"]


def test_approve_sets_approved_and_inbox_filters_it():
    store = Store(":memory:")
    client = client_for(store)
    case_id, pid = case_with_proposal(store, client, "k-ok")
    assert client.post(f"/proposals/{pid}/approve", json={"approver": "ops"}).status_code == 200
    assert _status(client, case_id) == "approved"
    assert [c["id"] for c in client.get("/cases?status=approved").json()] == [case_id]
    assert client.get("/cases?status=proposal_pending").json() == []


def test_reject_sets_rejected():
    store = Store(":memory:")
    client = client_for(store)
    case_id, pid = case_with_proposal(store, client, "k-no")
    body = {"approver": "ops", "reason": "no procede"}
    assert client.post(f"/proposals/{pid}/reject", json=body).status_code == 200
    assert _status(client, case_id) == "rejected"
    assert [c["id"] for c in client.get("/cases?status=rejected").json()] == [case_id]


def test_failed_execution_is_not_approved(monkeypatch):
    store = Store(":memory:")
    client = client_for(store)
    case_id, pid = case_with_proposal(store, client, "k-fail")

    def boom(store, proposal_id):
        raise RuntimeError("core caído")

    monkeypatch.setattr(service, "execute", boom)
    with pytest.raises(RuntimeError):
        service.approve(store, pid, "ops")
    assert _status(client, case_id) == "execution_failed"
    assert ledger.decision(store, pid)["decision"] == "approved"  # type: ignore[index]
    assert ledger.executions(store, pid) == []
    failures = [t for t in store.traces(case_id) if t["step"] == "execution_failed"]
    assert [t["payload"] for t in failures] == [{"kind": "RuntimeError"}]

    # Approve is idempotent: a retry executes and only then the case is approved.
    monkeypatch.undo()
    service.approve(store, pid, "ops")
    assert _status(client, case_id) == "approved"
    assert len(ledger.executions(store, pid)) == 1


def test_refused_action_via_api_is_execution_failed():
    store = Store(":memory:")
    client = client_for(store)
    case_id = post_ticket(client, key="k-ref", ticket_id="k-ref").json()["case_id"]
    pid = store.create_proposal(case_id, "refund", "txn_0166", "x", customer_id="cus_004")
    response = client.post(f"/proposals/{pid}/approve", json={"approver": "ops"})
    assert response.status_code == 422
    assert _status(client, case_id) == "execution_failed"


def test_approval_without_execution_is_never_approved():
    """The process dies between the decision and the execution: pessimistic status."""
    store = Store(":memory:")
    client = client_for(store)
    case_id, pid = case_with_proposal(store, client, "k-crash")
    ledger.record_decision(store, pid, approver="ops", decision="approved")
    assert _status(client, case_id) == "execution_failed"


def test_decided_statuses_are_terminal():
    store = Store(":memory:")
    client = client_for(store)
    approved_case, approved_pid = case_with_proposal(store, client, "k-t1")
    rejected_case, rejected_pid = case_with_proposal(store, client, "k-t2")
    client.post(f"/proposals/{approved_pid}/approve", json={"approver": "ops"})
    client.post(f"/proposals/{rejected_pid}/reject", json={"approver": "ops", "reason": ""})

    # Forbidden transitions still answer 409 and leave the status alone.
    reject_body = {"approver": "ops", "reason": ""}
    reject = client.post(f"/proposals/{approved_pid}/reject", json=reject_body)
    assert reject.status_code == 409
    approve = client.post(f"/proposals/{rejected_pid}/approve", json={"approver": "ops"})
    assert approve.status_code == 409
    assert _status(client, approved_case) == "approved"
    assert _status(client, rejected_case) == "rejected"

    # A late worker write (requeued job, or the status save racing an approval) is a no-op.
    store.set_case_status(approved_case, "proposal_pending")
    with store.connection:
        store.connection.execute("UPDATE jobs SET status = 'queued'")
    work(store, FakeModel())
    assert _status(client, approved_case) == "approved"
    assert _status(client, rejected_case) == "rejected"


@pytest.mark.parametrize("status", ["approved", "rejected", "execution_failed"])
def test_only_the_ledger_assigns_decided_statuses(status):
    store = Store(":memory:")
    client = client_for(store)
    case_id, _ = case_with_proposal(store, client, "k-only")
    with pytest.raises(ValueError):
        store.set_case_status(case_id, status)
    assert _status(client, case_id) == "proposal_pending"
