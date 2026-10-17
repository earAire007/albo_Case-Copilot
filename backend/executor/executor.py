"""Executor (spec 05a): runs an approved proposal, once. Invoked only by the approval flow
(specs 06/07), never by the orchestrator (import-linter).

Actions are stubs that record their effect. None moves money: the enum has no such action,
and an unknown action is refused even if someone approved it.
"""

from typing import Any

from backend.store.store import Store

ACTIONS: dict[str, str] = {
    "open_dispute": "aclaración registrada para revisión de operaciones",
    "resend_cep": "reenvío del comprobante CEP registrado",
    "escalate_fraud": "escalamiento a fraude registrado",
}


class NotApprovedError(PermissionError):
    pass


def execute(store: Store, proposal_id: int) -> dict[str, Any]:
    proposal = store.get_proposal(proposal_id)
    action = proposal["action"]
    if action not in ACTIONS:
        raise ValueError("acción fuera del enum: nunca se ejecuta")
    decision = store.decision(proposal_id)
    if decision is None or decision["decision"] != "approved":
        raise NotApprovedError("la propuesta no tiene una aprobación registrada")
    previous = store.executions(proposal_id)
    if previous:
        return previous[0]["result"]
    return store.record_execution(
        proposal_id,
        {
            "action": action,
            "txn_id": proposal["txn_id"],
            "effect": ACTIONS[action],
            "approved_by": decision["approver"],
        },
    )
