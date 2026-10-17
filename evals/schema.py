"""Eval case schema (spec 04). Shared by the label tests and the runner (cierre).

Labels come from the policies and the dataset, never from what an agent would do.
backend/ and mcp_server/ must not import this package (import-linter): the expected
labels never reach the agent.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

CASES_DIR = Path(__file__).resolve().parent / "cases"

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
Action = Literal["open_dispute", "resend_cep", "escalate_fraud", "none"]
Vector = Literal["customer_message", "policy_chunk", "tool_result", "other_account"]
MustNot = Literal[
    "propose_action_outside_enum",
    "act_without_approval",
    "reveal_identifier_digits",
    "mention_other_customer_data",
    "follow_injected_instruction",
    "claim_without_support",
]
ToolName = Literal[
    "get_customer",
    "list_transactions",
    "get_spei_status",
    "get_card_authorization",
    "search_policies",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExpectedTool(_Strict):
    name: ToolName
    args: dict[str, str] = Field(default_factory=dict)


class Expected(_Strict):
    case_type: CaseType
    action: Action
    tools: list[ExpectedTool]
    policy_chunks: list[str]
    no_support: bool
    must_not: list[MustNot] = Field(default_factory=list)
    justification: str = Field(min_length=1)


class Adversarial(_Strict):
    vectors: list[Vector] = Field(min_length=1)


class EvalCase(_Strict):
    id: str
    customer_id: str
    as_of: AwareDatetime
    message: str = Field(min_length=1)
    scenario_id: str | None
    expected: Expected
    adversarial: Adversarial | None


def load_cases(cases_dir: Path = CASES_DIR) -> list[EvalCase]:
    return [
        EvalCase.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(cases_dir.glob("*.json"))
    ]
