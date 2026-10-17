"""Spec 06 — API de aprobación: ejecuta una vez, estados terminales, approver no vacío,
y nada sensible en lo que verá la consola."""

import json

import pytest

from backend.domain.sensitive import find_sensitive
from backend.store import ledger
from backend.store.store import Store

from .spec06_helpers import case_with_proposal, client_for, post_ticket, work
from .test_loop import FakeModel, final


def test_approve_executes_once_and_reject_never_executes():
    store = Store(":memory:")
    client = client_for(store)
    _, approved = case_with_proposal(store, client, "k-a")
    first = client.post(f"/proposals/{approved}/approve", json={"approver": "ops@x"})
    second = client.post(f"/proposals/{approved}/approve", json={"approver": "ops@x"})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()
    assert len(ledger.executions(store, approved)) == 1

    _, rejected = case_with_proposal(store, client, "k-b")
    response = client.post(
        f"/proposals/{rejected}/reject", json={"approver": "ops@x", "reason": "no procede"}
    )
    assert response.status_code == 200
    assert ledger.executions(store, rejected) == []


@pytest.mark.parametrize(
    ("first", "then"),
    [("reject", "approve"), ("approve", "reject")],
    ids=["rejected→approve", "approved→reject"],
)
def test_terminal_transitions_are_forbidden(first, then):
    store = Store(":memory:")
    client = client_for(store)
    _, pid = case_with_proposal(store, client, "k-t")
    bodies = {"approve": {"approver": "ops@x"}, "reject": {"approver": "ops@x", "reason": "motivo"}}
    assert client.post(f"/proposals/{pid}/{first}", json=bodies[first]).status_code == 200
    before = (ledger.decision(store, pid), ledger.executions(store, pid))
    assert client.post(f"/proposals/{pid}/{then}", json=bodies[then]).status_code == 409
    assert (ledger.decision(store, pid), ledger.executions(store, pid)) == before


def test_empty_approver_is_rejected():
    store = Store(":memory:")
    client = client_for(store)
    _, pid = case_with_proposal(store, client, "k-e")
    for approver in ("", "   "):
        assert (
            client.post(f"/proposals/{pid}/approve", json={"approver": approver}).status_code == 422
        )
        assert (
            client.post(
                f"/proposals/{pid}/reject", json={"approver": approver, "reason": "x"}
            ).status_code
            == 422
        )
    assert ledger.decision(store, pid) is None


def test_unknown_proposal_is_404():
    client = client_for(Store(":memory:"))
    assert client.post("/proposals/999/approve", json={"approver": "ops"}).status_code == 404


def test_case_api_exposes_no_sensitive_data(raw_customers):
    store = Store(":memory:")
    client = client_for(store)
    c = next(x for x in raw_customers if x["id"] == "cus_004")
    case_id = post_ticket(
        client, key="k-s", message=f"Mi CLABE es {c['clabe']} y mi RFC {c['rfc']}"
    ).json()["case_id"]
    work(store, FakeModel(final()))
    listed = client.get("/cases").json()
    detail = client.get(f"/cases/{case_id}").json()
    trace = client.get(f"/cases/{case_id}/trace").json()
    assert any(item["id"] == case_id for item in listed)
    for payload in (listed, detail, trace):
        dumped = json.dumps(payload, ensure_ascii=False)
        assert find_sensitive(dumped) == []
        assert c["clabe"] not in dumped and c["rfc"] not in dumped
        assert '"thinking"' not in dumped
    assert detail["status"] == "answered" and detail["reply"]


def test_trace_view_hides_full_prompt():
    store = Store(":memory:")
    client = client_for(store)
    case_id = post_ticket(client, key="k-p").json()["case_id"]
    work(store, FakeModel(final()))
    # The 05b loop does not trace a "prompt" step; run_turn (05a) does. Insert one so the
    # filter is actually exercised.
    store.add_trace(case_id, "prompt", {"messages": [{"role": "user", "content": "x"}]})
    steps = {t["step"] for t in client.get(f"/cases/{case_id}/trace").json()}
    assert "prompt" not in steps and "model_step" in steps
