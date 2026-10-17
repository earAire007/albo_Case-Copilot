"""Approval flow (spec 06): the only caller of the executor besides tests, and one of the
two modules allowed to touch the ledger. Never touches the model (import-linter).

States are terminal: a rejected proposal cannot be approved and an approved one cannot be
rejected. Repeating approve on an approved proposal returns the same execution.

Reply edit (spec 07): allowed until the proposal is decided (always, if there is none),
serialized with approve/reject by the same store lock. Nothing is masked silently: a reply
with a digit run that is not a tracking key returned by this case's tools, or with an RFC
or CURP, is refused so the operator fixes it. Each decision snapshots the reply in force.
"""

from typing import Any

from backend.domain.sensitive import find_sensitive
from backend.executor.executor import execute
from backend.security.digits import has_digit_run, tracking_keys
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
        snapshot = current_reply(store, store.get_proposal(proposal_id)["case_id"])
        try:
            ledger.record_decision(
                store, proposal_id, approver=approver, decision="approved", reply_snapshot=snapshot
            )
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
    snapshot = current_reply(store, proposal["case_id"])
    try:
        ledger.record_decision(
            store, proposal_id, approver=approver, decision="rejected", reply_snapshot=snapshot
        )
    except ValueError as exc:
        raise ConflictError("la propuesta ya tiene una decisión") from exc
    store.add_trace(proposal["case_id"], "rejected_by_ops", {"reason": reason})
    decision = ledger.decision(store, proposal_id)
    assert decision is not None
    return decision


def decision_of(store: Store, proposal_id: int) -> dict[str, Any] | None:
    return ledger.decision(store, proposal_id)


def execution_of(store: Store, proposal_id: int) -> dict[str, Any] | None:
    previous = ledger.executions(store, proposal_id)
    return previous[0] if previous else None


def model_reply(store: Store, case_id: str) -> str | None:
    answers = [t for t in store.traces(case_id) if t["step"] == "answer"]
    return answers[-1]["payload"].get("customer_reply") if answers else None


def current_reply(store: Store, case_id: str) -> str | None:
    """The human edit if there is one, otherwise the model's reply (None without a case)."""
    try:
        case = store.get_case(case_id)
    except KeyError:
        return None
    return case["final_reply"] if case["final_reply"] is not None else model_reply(store, case_id)


def edit_reply(store: Store, case_id: str, editor: str, final_reply: str) -> dict[str, Any]:
    editor = _check_editor(editor)
    with store.lock:
        store.get_case(case_id)  # KeyError -> 404
        proposal = store.proposal_for_case(case_id)
        if proposal is not None and ledger.decision(store, proposal["id"]) is not None:
            raise ConflictError("la propuesta ya tiene una decisión: la respuesta no se edita")
        _check_reply(store, case_id, final_reply)
        store.set_final_reply(case_id, final_reply, editor=editor)
        store.add_trace(case_id, "reply_edited", {"editor": editor})
        return store.get_case(case_id)


def _check_editor(editor: str) -> str:
    if not editor.strip():
        raise ValueError("editor vacío")
    return editor.strip()


def _check_reply(store: Store, case_id: str, text: str) -> None:
    if not text.strip():
        raise ValueError("la respuesta está vacía")
    results = (
        t["payload"].get("payload") for t in store.traces(case_id) if t["step"] == "tool_result"
    )
    if has_digit_run(text, tracking_keys(results)):
        raise ValueError(
            "la respuesta contiene un tramo de 13 o más dígitos que no es una clave de rastreo"
            " devuelta por las herramientas de este caso; quítalo o usa la terminación"
        )
    if find_sensitive(text):
        raise ValueError("la respuesta contiene un RFC o una CURP; quítalo antes de guardar")
