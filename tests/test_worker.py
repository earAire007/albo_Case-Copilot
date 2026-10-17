"""Spec 06 — cola en proceso: procesa, recupera jobs colgados, falla a humano, no duplica."""

import sqlite3

import pytest

from backend.store.store import Store

from .spec06_helpers import LATER, RECEIVED, case_with_proposal, client_for, post_ticket, work
from .test_loop import FakeModel, final


def _case(client, store, case_id):
    return client.get(f"/cases/{case_id}").json()


def test_worker_processes_queued_case():
    store = Store(":memory:")
    client = client_for(store)
    case_id = post_ticket(client).json()["case_id"]
    assert work(store, FakeModel(final())) == case_id
    assert _case(client, store, case_id)["status"] == "answered"
    assert work(store, FakeModel()) is None, "no queda trabajo"


def test_stuck_job_is_recovered():
    store = Store(":memory:")
    client = client_for(store)
    case_id = post_ticket(client).json()["case_id"]
    claimed = store.claim_job(now=RECEIVED)  # a worker took it and died
    assert claimed is not None
    assert work(store, FakeModel(), now=RECEIVED) is None, "todavía no se considera colgado"
    assert work(store, FakeModel(final()), now=LATER) == case_id
    assert _case(client, store, case_id)["status"] == "answered"


def test_job_failing_twice_requires_human():
    store = Store(":memory:")
    client = client_for(store)
    case_id = post_ticket(client).json()["case_id"]
    model = FakeModel(RuntimeError("caída"), RuntimeError("caída"))
    work(store, model)
    assert _case(client, store, case_id)["status"] == "queued", "primer fallo: se reintenta"
    work(store, model)
    assert _case(client, store, case_id)["status"] == "requires_human"
    (job,) = store.all_rows()["jobs"]
    assert job["status"] == "failed" and len(model.requests) == 2


def test_requeued_job_does_not_duplicate_proposal_or_model_calls():
    store = Store(":memory:")
    client = client_for(store)
    case_id, _ = case_with_proposal(store, client, "k-dup")
    with store.connection:
        store.connection.execute("UPDATE jobs SET status = 'queued' WHERE case_id = ?", (case_id,))
    idle = FakeModel()
    work(store, idle)
    assert idle.requests == [], "un caso con propuesta no vuelve a llamar al modelo"
    assert len(store.all_rows()["proposals"]) == 1
    with pytest.raises(sqlite3.IntegrityError):
        store.create_proposal(case_id, "open_dispute", "txn_0166", "otra", customer_id="cus_004")


def test_case_with_proposal_left_queued_is_closed_as_pending():
    """The worker died after run_case created the proposal but before saving the status."""
    store = Store(":memory:")
    client = client_for(store)
    case_id, _ = case_with_proposal(store, client, "k-q")
    store.set_case_status(case_id, "queued")
    with store.connection:
        store.connection.execute("UPDATE jobs SET status = 'queued' WHERE case_id = ?", (case_id,))
    work(store, FakeModel())
    assert _case(client, store, case_id)["status"] == "proposal_pending"


def test_stuck_job_out_of_attempts_requires_human():
    store = Store(":memory:")
    client = client_for(store)
    case_id = post_ticket(client).json()["case_id"]
    store.claim_job(now=RECEIVED)
    with store.connection:
        store.connection.execute("UPDATE jobs SET attempts = 2 WHERE case_id = ?", (case_id,))
    idle = FakeModel()
    work(store, idle, now=LATER)
    assert idle.requests == [], "no se reprocesa sin límite"
    assert _case(client, store, case_id)["status"] == "requires_human"


def test_requeued_job_of_finished_case_is_skipped():
    store = Store(":memory:")
    client = client_for(store)
    case_id = post_ticket(client).json()["case_id"]
    work(store, FakeModel(final()))
    assert _case(client, store, case_id)["status"] == "answered"
    with store.connection:
        store.connection.execute("UPDATE jobs SET status = 'queued' WHERE case_id = ?", (case_id,))
    idle = FakeModel()
    assert work(store, idle) is None
    assert idle.requests == [] and _case(client, store, case_id)["status"] == "answered"
