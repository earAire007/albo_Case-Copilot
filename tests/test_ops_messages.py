"""Mensajes 422 para operaciones (ajuste cosmético tras el clon limpio): dicen qué hacer,
sin jerga interna. Las reglas no cambian; solo el texto."""

from backend.store.store import Store

from .spec06_helpers import case_with_proposal, client_for

EMPTY_EDITOR = "Escribe tu nombre en Operador antes de guardar."
EMPTY_APPROVER = "Escribe tu nombre en Operador antes de aprobar o rechazar."
DIGITS = (
    "La respuesta parece contener un número de cuenta o tarjeta completo. "
    "Quítalo o usa solo los últimos 4 dígitos."
)


def test_empty_operator_messages():
    store = Store(":memory:")
    client = client_for(store)
    case_id, pid = case_with_proposal(store, client, "k-msg")
    edit = client.put(f"/cases/{case_id}/reply", json={"editor": " ", "final_reply": "Hola."})
    assert (edit.status_code, edit.json()["detail"]) == (422, EMPTY_EDITOR)
    for path, body in (
        (f"/proposals/{pid}/approve", {"approver": ""}),
        (f"/proposals/{pid}/reject", {"approver": "", "reason": "x"}),
    ):
        response = client.post(path, json=body)
        assert (response.status_code, response.json()["detail"]) == (422, EMPTY_APPROVER)


def test_digit_run_message():
    store = Store(":memory:")
    client = client_for(store)
    case_id, _ = case_with_proposal(store, client, "k-dig")
    body = {"editor": "ops", "final_reply": "Tu tarjeta 4111 2222 3333 4444 ya quedó"}
    response = client.put(f"/cases/{case_id}/reply", json=body)
    assert (response.status_code, response.json()["detail"]) == (422, DIGITS)
