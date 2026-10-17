"""Tool-calling loop with the real model (spec 05b).

The model sees the tools of the MCP session bound to the case's customer plus
`search_policies`. Every tool result enters the conversation masked and delimited. The
final output goes through the same validation as spec 05a and ends as a pending proposal,
an answer, or a case for a human. Never executes.

Failure policy:
- timeout / rate limit / 5xx / connection: retried with exponential backoff and jitter;
  exhausted -> human. Non-retryable provider errors (4xx) -> human at once, traced by
  kind (never the SDK message). A tool that raises or returns non-JSON goes back to the
  model as a tool error.
- refusal / max_tokens: human (no server-side fallbacks: retrying adversarial content on
  another model is shopping for one that accepts the injection).
- format rejections (schema, no_support): one repair turn with generic reasons, never
  the rejected text. Security or support rejections: straight to a human.
- budget (tool steps, tokens) exceeded: human.
"""

import json
import random
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import anyio

from backend.agent.injection_detector import Vector, scan
from backend.agent.model import (
    ModelRequestError,
    ModelStep,
    TextBlock,
    ToolCall,
    ToolCallingModel,
    ToolSpec,
    TransientModelError,
)
from backend.agent.prompt import ACTION_TYPES, CASE_TYPES, SYSTEM, build_prompt, untrusted_block
from backend.agent.validators import CaseContext, Rejection, ToolResult, evaluate
from backend.orchestrator.turn import TurnResult, conclude, record_rejections
from backend.policies.retrieval import search_policies
from backend.security.masking import Json
from backend.store.store import Store

FORMAT_VALIDATORS = frozenset({"schema", "no_support"})

SEARCH_POLICIES = ToolSpec(
    name="search_policies",
    description=(
        "Busca fragmentos de las políticas internas. Devuelve hasta k fragmentos con su id "
        "(doc#seccion) para citar, o una lista vacía si ninguna política lo sustenta."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Qué buscar, en español."},
            "k": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)


@dataclass(frozen=True)
class LoopConfig:
    price_input_per_mtok: float
    price_output_per_mtok: float
    max_tool_steps: int = 6
    max_case_tokens: int = 30_000
    max_retries: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0


class ToolSession(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...

    async def call_tool(self, name: str, args: Mapping[str, Any]) -> tuple[bool, str]: ...


@dataclass
class _CaseState:
    tool_results: list[ToolResult]
    chunks: dict[str, str]
    tool_steps: int = 0
    tokens: int = 0
    repaired: bool = False


def _signal(store: Store, ctx: CaseContext, vector: Vector, text: str) -> None:
    signal = scan(vector, text)
    store.add_trace(
        ctx.case_id,
        "injection_signal",
        {"vector": vector, "detected": signal.detected, "patterns": list(signal.patterns)},
    )


def _stop(store: Store, ctx: CaseContext, reason: str) -> TurnResult:
    store.add_trace(ctx.case_id, "stop", {"reason": reason})
    return TurnResult("requires_human")


def _cost(step: ModelStep, config: LoopConfig) -> float:
    usage = step.usage
    total = usage.input_tokens * config.price_input_per_mtok
    total += usage.output_tokens * config.price_output_per_mtok
    return round(total / 1_000_000, 6)


async def _call_model(
    store: Store,
    ctx: CaseContext,
    model: ToolCallingModel,
    messages: list[dict[str, Any]],
    tools: Sequence[ToolSpec],
    config: LoopConfig,
    sleep: Callable[[float], Awaitable[None]],
    clock: Callable[[], float],
    rng: random.Random,
) -> tuple[ModelStep, int, float] | str:
    """The step, retries and latency; or the stop reason if the provider failed."""
    for attempt in range(config.max_retries + 1):
        started = clock()
        try:
            step = await model.step(SYSTEM, list(messages), tools)
        except ModelRequestError as exc:
            store.add_trace(ctx.case_id, "provider_error", {"kind": exc.kind, "attempt": attempt})
            return "provider_error"
        except TransientModelError as exc:
            store.add_trace(ctx.case_id, "provider_error", {"kind": exc.kind, "attempt": attempt})
            if attempt == config.max_retries:
                return "provider_unavailable"
            delay = config.base_delay_s * 2**attempt + rng.uniform(0, config.base_delay_s)
            await sleep(min(delay, config.max_delay_s))
            continue
        return step, attempt, (clock() - started) * 1000
    return "provider_unavailable"


async def _run_tool(
    store: Store, ctx: CaseContext, session: ToolSession, call: ToolCall, state: _CaseState
) -> tuple[bool, str]:
    if call.name == SEARCH_POLICIES.name:
        try:
            query = str(call.input["query"])
            results = search_policies(query, int(call.input.get("k", 3)))
        except (KeyError, TypeError, ValueError):
            return True, untrusted_block("herramienta:search_policies", "argumentos inválidos")
        # Spec 08: ids only (recall of policy_chunks); the texts stay out of the trace.
        store.add_trace(ctx.case_id, "policy_result", {"ids": [str(r["id"]) for r in results]})
        new_texts = [str(r["text"]["untrusted_text"]) for r in results]
        for r in results:
            state.chunks[str(r["id"])] = str(r["text"]["untrusted_text"])
        if new_texts:
            _signal(store, ctx, "policy_chunk", "\n".join(new_texts))
        payload = json.dumps(results, ensure_ascii=False)
        return False, untrusted_block("politica", payload)

    source = f"herramienta:{call.name}"
    try:
        is_error, text = await session.call_tool(call.name, call.input)
    except Exception as exc:
        # Never echo the exception: it may carry anything. Ops get its type; the model
        # gets a generic tool error.
        store.add_trace(ctx.case_id, "tool_error", {"tool": call.name, "kind": type(exc).__name__})
        return True, untrusted_block(source, "error al ejecutar la herramienta")
    if is_error:
        return True, untrusted_block(source, text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return True, untrusted_block(source, "la herramienta devolvió una respuesta inválida")
    state.tool_results.append(ToolResult(call.name, dict(call.input), payload))
    # Spec 07: the console shows it, and the reply edit exempts only tracking keys found here.
    store.add_trace(ctx.case_id, "tool_result", {"tool": call.name, "payload": payload})
    _signal(store, ctx, "tool_result", text)
    return False, untrusted_block(source, text)


def _repair_note(rejections: Sequence[Rejection]) -> str:
    names = ", ".join(sorted({r.validator for r in rejections}))
    return (
        f"Tu respuesta anterior no cumplió el formato ({names}). Responde de nuevo solo con "
        "el objeto JSON del esquema, sin bloques de código; si no citas políticas, marca "
        f"no_support en true. case_type debe ser uno de: {CASE_TYPES}. action es null o "
        f"tiene type igual a uno de: {ACTION_TYPES}."
    )


async def run_case(
    store: Store,
    ctx: CaseContext,
    session: ToolSession,
    model: ToolCallingModel,
    config: LoopConfig,
    *,
    sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
    clock: Callable[[], float] = time.monotonic,
    rng: random.Random | None = None,
) -> TurnResult:
    rng = rng or random.Random()
    state = _CaseState(tool_results=[], chunks={})
    _signal(store, ctx, "customer_message", ctx.message)
    tools = [*await session.list_tools(), SEARCH_POLICIES]
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": build_prompt(ctx, [], [])[1]["content"]}
    ]

    while True:
        called = await _call_model(store, ctx, model, messages, tools, config, sleep, clock, rng)
        if isinstance(called, str):
            return _stop(store, ctx, called)
        step, retries, latency_ms = called
        # Without prompt caching today; if enabled, add cache_creation/cache_read tokens
        # here and in _cost.
        state.tokens += step.usage.input_tokens + step.usage.output_tokens
        calls = [b for b in step.blocks if isinstance(b, ToolCall)]
        texts = [b.text for b in step.blocks if isinstance(b, TextBlock)]
        trace: dict[str, Json] = {
            "model": step.model,
            "stop_reason": step.stop_reason,
            "input_tokens": step.usage.input_tokens,
            "output_tokens": step.usage.output_tokens,
            "cost_usd": _cost(step, config),
            "latency_ms": round(latency_ms, 1),
            "retries": retries,
            "text": list[Json](texts),
            "tool_calls": [{"name": c.name, "input": json.dumps(dict(c.input))} for c in calls],
        }
        # Opaque blocks (thinking) go back to the model unchanged but are never traced.
        store.add_trace(ctx.case_id, "model_step", trace)

        if state.tokens > config.max_case_tokens:
            return _stop(store, ctx, "budget_tokens")
        if step.stop_reason in ("refusal", "max_tokens"):
            return _stop(store, ctx, step.stop_reason)

        if calls:
            state.tool_steps += len(calls)
            if state.tool_steps > config.max_tool_steps:
                return _stop(store, ctx, "budget_steps")
            messages.append({"role": "assistant", "content": list(step.blocks)})
            results: list[dict[str, Any]] = []
            for call in calls:
                is_error, content = await _run_tool(store, ctx, session, call, state)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": content,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": results})
            continue

        raw = "".join(texts)
        output, rejections = evaluate(raw, ctx, state.tool_results, set(state.chunks))
        if rejections or output is None:
            record_rejections(store, ctx, raw, rejections)
            format_only = all(r.validator in FORMAT_VALIDATORS for r in rejections)
            if format_only and not state.repaired:
                state.repaired = True
                messages.append({"role": "assistant", "content": list(step.blocks)})
                messages.append({"role": "user", "content": _repair_note(rejections)})
                continue
            return TurnResult("requires_human", rejections=rejections)
        return conclude(store, ctx, output)
