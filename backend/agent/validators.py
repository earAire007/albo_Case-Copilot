"""Deterministic output validators (spec 05a). Pure functions over the parsed output and
what this case actually saw (tool results and retrieved chunks).

Any rejection discards the whole output: the case goes to a human, nothing is proposed.
Each rejection names its validator, which feeds the rejected-outputs metric.
"""

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from backend.agent.output import AgentOutput, OutputSchemaError, parse_output
from backend.security.digits import has_digit_run, tracking_keys
from backend.security.digits import walk as _walk

_AMOUNT = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?")
_TXN_ID = re.compile(r"\btxn_\d{4}\b")
_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class CaseContext:
    case_id: str
    customer_id: str
    as_of: datetime
    message: str


@dataclass(frozen=True)
class ToolResult:
    name: str
    args: Mapping[str, object]
    payload: object


@dataclass(frozen=True)
class Rejection:
    validator: str
    reason: str


def _known_txns(tool_results: Sequence[ToolResult]) -> dict[str, str]:
    """txn id -> customer_id, from every movement the tools returned."""
    txns: dict[str, str] = {}
    for result in tool_results:
        for node in _walk(result.payload):
            txn_id = node.get("txn_id", node.get("id"))
            owner = node.get("customer_id")
            if isinstance(txn_id, str) and txn_id.startswith("txn_") and isinstance(owner, str):
                txns[txn_id] = owner
    return txns


def _known_amounts(tool_results: Sequence[ToolResult]) -> set[Decimal]:
    """Amounts in pesos; the tools return cents."""
    amounts: set[Decimal] = set()
    for result in tool_results:
        for node in _walk(result.payload):
            cents = node.get("amount")
            if isinstance(cents, int) and not isinstance(cents, bool):
                amounts.add((Decimal(cents) / 100).quantize(_CENTS))
    return amounts


def _amount(match: re.Match[str]) -> Decimal:
    whole = match.group(1).replace(",", "")
    fraction = match.group(2) or "0"
    return Decimal(f"{whole}.{fraction}").quantize(_CENTS)


def check_action(
    output: AgentOutput, ctx: CaseContext, tools: Sequence[ToolResult]
) -> list[Rejection]:
    if output.action is None:
        return []
    owner = _known_txns(tools).get(output.action.txn_id)
    if owner is None:
        return [Rejection("action", "el movimiento de la acción no aparece en los resultados")]
    if owner != ctx.customer_id:
        return [Rejection("action", "el movimiento de la acción no es del cliente del caso")]
    return []


def check_citations(output: AgentOutput, chunk_ids: Collection[str]) -> list[Rejection]:
    return [
        Rejection("citations", "cita un chunk que no fue recuperado")
        for cite in output.citations
        if cite not in chunk_ids
    ]


def check_digits(output: AgentOutput, tools: Sequence[ToolResult]) -> list[Rejection]:
    """Only tracking keys that this case's tools returned are exempt, never the format."""
    texts = [output.customer_reply, output.reasoning_summary]
    if output.action is not None:
        texts.append(output.action.justification)
    exempt = tracking_keys(result.payload for result in tools)
    if any(has_digit_run(text, exempt) for text in texts):
        return [Rejection("digits", "la salida contiene un tramo de 13 o más dígitos")]
    return []


def check_facts(
    output: AgentOutput, ctx: CaseContext, tools: Sequence[ToolResult]
) -> list[Rejection]:
    rejections: list[Rejection] = []
    amounts = _known_amounts(tools)
    if any(_amount(m) not in amounts for m in _AMOUNT.finditer(output.customer_reply)):
        rejections.append(Rejection("facts", "menciona un monto sin sustento en las tools"))
    txns = _known_txns(tools)
    for txn_id in _TXN_ID.findall(output.customer_reply):
        if txns.get(txn_id) != ctx.customer_id:
            rejections.append(Rejection("facts", "menciona un movimiento sin sustento"))
            break
    return rejections


def check_no_support(output: AgentOutput) -> list[Rejection]:
    if output.no_support and output.citations:
        return [Rejection("no_support", "declara no_support pero cita políticas")]
    if not output.no_support and not output.citations:
        return [Rejection("no_support", "afirma sin citas y sin declarar no_support")]
    return []


def evaluate(
    raw: str, ctx: CaseContext, tools: Sequence[ToolResult], chunk_ids: Collection[str]
) -> tuple[AgentOutput | None, list[Rejection]]:
    try:
        output = parse_output(raw)
    except OutputSchemaError as exc:
        return None, [Rejection("schema", str(exc))]
    rejections = [
        *check_action(output, ctx, tools),
        *check_citations(output, chunk_ids),
        *check_digits(output, tools),
        *check_facts(output, ctx, tools),
        *check_no_support(output),
    ]
    return output, rejections
