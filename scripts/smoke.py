"""Smoke run with the real model (spec 05b). Costs money and is not deterministic:
never part of `make test` or `make check`. Requires Anthropic credentials.

Usage: make smoke   (or: uv run python scripts/smoke.py 02 10 13)
"""

import os
import sys
from pathlib import Path

import anyio
from mcp import Client

from backend.agent.validators import CaseContext
from backend.llm.anthropic_client import AnthropicModel, LlmSettings
from backend.mock_core.repository import JsonCoreRepository
from backend.orchestrator.loop import LoopConfig, run_case
from backend.orchestrator.mcp_session import McpToolSession
from backend.store.store import Store
from evals.runner import opaque_id
from evals.schema import load_cases
from mcp_server.server import create_server

DEFAULT_CASES = ("02", "10", "13")


def _config() -> LoopConfig:
    # Defaults verified against the official model table (claude-opus-5-5: $4 / $20 per
    # MTok, 2026-10-06); override per variant in .env.
    return LoopConfig(
        price_input_per_mtok=float(os.environ.get("PRICE_INPUT_PER_MTOK", "4.0")),
        price_output_per_mtok=float(os.environ.get("PRICE_OUTPUT_PER_MTOK", "20.0")),
        max_tool_steps=int(os.environ.get("MAX_TOOL_STEPS", "6")),
        max_case_tokens=int(os.environ.get("MAX_CASE_TOKENS", "30000")),
    )


async def main(prefixes: list[str]) -> None:
    store = Store(Path("var") / "smoke.db")
    model = AnthropicModel(LlmSettings.from_env())
    config = _config()
    repo = JsonCoreRepository()
    for case in load_cases():
        if case.id[:2] not in prefixes:
            continue
        # Opaque id: the eval id names the attack and the prompt carries it (spec 08, H1).
        ctx = CaseContext(opaque_id(case), case.customer_id, case.as_of, case.message)
        async with Client(create_server(repo, case.customer_id)) as client:
            result = await run_case(store, ctx, McpToolSession(client), model, config)
        steps = [t for t in store.traces(ctx.case_id) if t["step"] == "model_step"]
        tokens = sum(s["payload"]["input_tokens"] + s["payload"]["output_tokens"] for s in steps)
        cost = sum(s["payload"]["cost_usd"] for s in steps)
        print(
            f"{case.id}: {result.status} (esperado: {case.expected.action}) "
            f"pasos={len(steps)} tokens={tokens} costo_usd={cost:.4f}"
        )


if __name__ == "__main__":
    anyio.run(main, sys.argv[1:] or list(DEFAULT_CASES))
