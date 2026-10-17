"""Spec 07 — edición persistente de la respuesta, snapshot en la decisión, traza
`tool_result` y versión del esquema."""

import json
import sqlite3

import pytest

from backend.domain.sensitive import find_sensitive
from backend.store.store import Store
from evals.schema import load_cases

from .spec06_helpers import case_with_proposal, client_for, post_ticket, work
from .test_loop import FakeModel, call, final, run, step, steps_of

TRACKING_KEY = "CC202608196242461589"  # txn_0060, spei_in of cus_004


def _answered_case_with_spei(store, client, key="k-spei"):
    """The model looked up the SPEI movements, so the case's tools returned TRACKING_KEY."""
    case_id = post_ticket(client, key=key, ticket_id=key).json()["case_id"]
    work(store, FakeModel(step(call("list_transactions", {"type": "spei_in"})), final()))
    assert client.get(f"/cases/{case_id}").json()["status"] == "answered"
    return case_id


def _edit(client, case_id, text, editor="ops"):
    return client.put(f"/cases/{case_id}/reply", json={"editor": editor, "final_reply": text})


# --- AC1-2: persist, reject digit runs without silent masking, provenance exemption ---


def test_edit_reply_persists(raw_customers):
    store = Store(":memory:")
    client = client_for(store)
    case_id = _answered_case_with_spei(store, client)
    model_reply = client.get(f"/cases/{case_id}").json()["reply"]

    assert _edit(client, case_id, "Hola, ya revisamos tu cargo.").status_code == 200
    view = client.get(f"/cases/{case_id}").json()
    assert view["final_reply"] == "Hola, ya revisamos tu cargo."
    assert view["reply"] == model_reply, "la respuesta del modelo se conserva"

    clabe = raw_customers[0]["clabe"]
    for text in ("Tu tarjeta 4111 2222 3333 4444 ya quedó", f"Tu CLABE es {clabe}"):
        response = _edit(client, case_id, text)
        assert response.status_code == 422, text
        assert "dígitos" in response.json()["detail"]
        assert client.get(f"/cases/{case_id}").json()["final_reply"] == (
            "Hola, ya revisamos tu cargo."
        ), "sin enmascarado silencioso: no se guarda nada"

    accepted = f"Tu transferencia con clave de rastreo {TRACKING_KEY} llegó."
    assert _edit(client, case_id, accepted).status_code == 200
    assert client.get(f"/cases/{case_id}").json()["final_reply"] == accepted


def test_edit_reply_rejects_unproven_tracking_key(raw_customers):
    store = Store(":memory:")
    client = client_for(store)
    case_id = _answered_case_with_spei(store, client)
    disguised = "CC" + raw_customers[0]["clabe"]  # tracking-key format, not from the tools
    response = _edit(client, case_id, f"Tu clave de rastreo es {disguised}")
    assert response.status_code == 422
    assert client.get(f"/cases/{case_id}").json()["final_reply"] is None


# --- AC3: rules ---


def test_edit_reply_rules():
    store = Store(":memory:")
    client = client_for(store)
    case_id, proposal_id = case_with_proposal(store, client, "k-rules")
    assert _edit(client, case_id, "texto", editor="  ").status_code == 422
    assert _edit(client, "case_nope", "texto").status_code == 404
    assert _edit(client, case_id, "antes de decidir").status_code == 200
    client.post(f"/proposals/{proposal_id}/approve", json={"approver": "ops"})
    response = _edit(client, case_id, "después de decidir")
    assert response.status_code == 409
    assert client.get(f"/cases/{case_id}").json()["final_reply"] == "antes de decidir"


# --- AC4: trace and snapshot ---


def test_reply_edit_is_traced(raw_customers):
    store = Store(":memory:")
    client = client_for(store)
    case_id = _answered_case_with_spei(store, client)
    clabe = raw_customers[0]["clabe"]
    assert _edit(client, case_id, "Listo.", editor=f"ops {clabe}").status_code == 200
    trace = client.get(f"/cases/{case_id}/trace").json()
    (edit,) = [t for t in trace if t["step"] == "reply_edited"]
    dumped = json.dumps(edit, ensure_ascii=False)
    assert clabe not in dumped and find_sensitive(dumped) == []
    assert edit["payload"]["editor"] == f"ops ****{clabe[-4:]}"
    view = client.get(f"/cases/{case_id}").json()
    assert view["edited_by"] == f"ops ****{clabe[-4:]}" and view["edited_at"]


def test_decision_snapshots_current_reply():
    store = Store(":memory:")
    client = client_for(store)

    edited_case, edited_pid = case_with_proposal(store, client, "k-snap-a")
    _edit(client, edited_case, "Abrimos la aclaración de tu cargo duplicado.")
    client.post(f"/proposals/{edited_pid}/approve", json={"approver": "ops"})
    approved = client.get(f"/cases/{edited_case}").json()["proposal"]["decision"]
    assert approved["reply_snapshot"] == "Abrimos la aclaración de tu cargo duplicado."

    plain_case, plain_pid = case_with_proposal(store, client, "k-snap-b")
    model_reply = client.get(f"/cases/{plain_case}").json()["reply"]
    client.post(f"/proposals/{plain_pid}/reject", json={"approver": "ops", "reason": "no"})
    rejected = client.get(f"/cases/{plain_case}").json()["proposal"]["decision"]
    assert rejected["reply_snapshot"] == model_reply, "sin edición: la del modelo"


# --- tool_result trace (change to 05b) and its coverage in persisted data ---


def test_loop_traces_tool_results_masked(raw_transactions):
    model = FakeModel(step(call("list_transactions", {"type": "spei_in"})), final())
    _, store = run(model)
    (row,) = steps_of(store, "tool_result")
    assert row["payload"]["tool"] == "list_transactions"
    dumped = json.dumps(row, ensure_ascii=False)
    assert TRACKING_KEY in dumped, "la clave de rastreo sobrevive: de ahí sale la exención"
    clabes = {t["counterparty_clabe"] for t in raw_transactions if t.get("counterparty_clabe")}
    assert find_sensitive(dumped) == [] and not any(c in dumped for c in clabes)


def test_persisted_rows_after_loop_have_no_sensitive_data(raw_customers, raw_transactions):
    """Like test_persisted_traces_have_no_sensitive_data (05a), but through run_case, so
    the tool_result rows are covered too."""
    secrets = {c[f] for c in raw_customers for f in ("clabe", "card_number", "rfc", "curp")}
    secrets |= {t["counterparty_clabe"] for t in raw_transactions if t.get("counterparty_clabe")}
    seen_tool_results = 0
    for case in load_cases():
        tools = case.expected.tools
        calls = [call(t.name, dict(t.args), call_id=f"t{i}") for i, t in enumerate(tools)]
        model = FakeModel(step(*calls), final()) if calls else FakeModel(final())
        _, store = run(model, customer_id=case.customer_id, message=case.message)
        seen_tool_results += len(steps_of(store, "tool_result"))
        for table in store.all_rows().values():
            for row in table:
                dumped = json.dumps(row, ensure_ascii=False)
                assert find_sensitive(dumped) == [], (case.id, row)
                assert not any(s in dumped for s in secrets), (case.id, row)
    assert seen_tool_results > 0


# --- schema version ---


def test_outdated_schema_fails_with_clear_message(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE cases (id TEXT PRIMARY KEY)")  # a pre-07 database
    old.commit()
    old.close()
    with pytest.raises(RuntimeError, match="esquema desactualizado: borra var/copilot.db"):
        Store(path)


def test_fresh_and_current_databases_open(tmp_path):
    path = tmp_path / "new.db"
    Store(path)
    Store(path)  # reopening a current database works
