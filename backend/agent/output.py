"""Structured output the model must produce (spec 05a). Parsing is strict: anything else is
rejected and the case goes to a human.
"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Same values as evals/schema.py CaseType; kept in sync by a test, never by import
# (the agent must not import eval labels).
CaseType = Literal[
    "spei_pendiente",
    "spei_devuelto",
    "comprobante_cep",
    "cargo_duplicado",
    "cargo_no_reconocido",
    "compra_rechazada",
    "privacidad",
    "fuera_de_politica",
    "solicitud_improcedente",
]
# Closed enum (invariant 2). There is no money-moving action.
ActionType = Literal["open_dispute", "resend_cep", "escalate_fraud"]


class OutputSchemaError(ValueError):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProposedAction(_Strict):
    type: ActionType
    txn_id: str = Field(min_length=1)
    justification: str = Field(min_length=1)


class AgentOutput(_Strict):
    case_type: CaseType
    customer_reply: str
    reasoning_summary: str
    action: ProposedAction | None
    citations: list[str]
    no_support: bool


def parse_output(raw: str) -> AgentOutput:
    try:
        return AgentOutput.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        # Never echo the payload: it is model output and may carry anything.
        raise OutputSchemaError("la salida no cumple el esquema") from exc
