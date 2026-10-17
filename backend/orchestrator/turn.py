"""One harness turn (spec 05a): prompt -> model -> validation -> proposal or human.

Receives tool results and chunks from the caller; the tool-calling loop is spec 05b.
Never executes: a valid action only becomes a pending proposal (import-linter keeps the
executor out of reach).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from backend.agent.model import ModelClient
from backend.agent.output import AgentOutput
from backend.agent.prompt import build_prompt
from backend.agent.validators import CaseContext, Rejection, ToolResult, evaluate
from backend.security.masking import Json
from backend.store.store import Store

Status = Literal["proposal_pending", "answered", "requires_human"]


@dataclass(frozen=True)
class TurnResult:
    status: Status
    proposal_id: int | None = None
    output: AgentOutput | None = None
    rejections: list[Rejection] = field(default_factory=list[Rejection])


def run_turn(
    store: Store,
    ctx: CaseContext,
    tool_results: Sequence[ToolResult],
    chunks: Sequence[Mapping[str, str]],
    model: ModelClient,
) -> TurnResult:
    messages = build_prompt(ctx, tool_results, chunks)
    prompt_trace: list[Json] = [{"role": m["role"], "content": m["content"]} for m in messages]
    store.add_trace(ctx.case_id, "prompt", {"messages": prompt_trace})
    raw = model.complete(messages)
    store.add_trace(ctx.case_id, "model_output", {"raw": raw})

    output, rejections = evaluate(raw, ctx, tool_results, {c["id"] for c in chunks})
    if rejections or output is None:
        record_rejections(store, ctx, raw, rejections)
        return TurnResult("requires_human", rejections=rejections)
    return conclude(store, ctx, output)


def record_rejections(
    store: Store, ctx: CaseContext, raw: str, rejections: Sequence[Rejection]
) -> None:
    """Every rejection is traced with its validator (rejected-outputs metric)."""
    for rejection in rejections:
        store.add_trace(
            ctx.case_id,
            "rejection",
            {"reason": rejection.reason, "output": raw},
            validator=rejection.validator,
        )


def conclude(store: Store, ctx: CaseContext, output: AgentOutput) -> TurnResult:
    """A validated output: answer, or a pending proposal. Never executes."""
    store.add_trace(ctx.case_id, "validation", {"status": "ok"})
    store.add_trace(ctx.case_id, "reasoning_summary", {"text": output.reasoning_summary})
    if output.action is None:
        return TurnResult("answered", output=output)
    proposal_id = store.create_proposal(
        ctx.case_id, output.action.type, output.action.txn_id, output.action.justification
    )
    store.add_trace(
        ctx.case_id,
        "proposal",
        {"proposal_id": proposal_id, "action": output.action.type, "txn_id": output.action.txn_id},
    )
    return TurnResult("proposal_pending", proposal_id=proposal_id, output=output)
