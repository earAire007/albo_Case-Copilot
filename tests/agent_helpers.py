"""Shared helpers for the spec 05a tests: case context, tool results and a scripted model."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import anyio
from mcp import Client
from mcp.types import TextContent

from backend.agent.validators import CaseContext, ToolResult
from backend.mock_core.repository import JsonCoreRepository
from mcp_server.server import create_server

REPO_ROOT = Path(__file__).resolve().parent.parent
AS_OF = datetime.fromisoformat(
    json.loads((REPO_ROOT / "data" / "scenarios.json").read_text())["reference_date"]
)


class ScriptedModel:
    """ModelClient double: returns canned outputs and records what it was sent."""

    def __init__(self, *outputs: str) -> None:
        self._outputs = list(outputs)
        self.received: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.received.append(messages)
        return self._outputs.pop(0)


def output_json(**overrides: Any) -> str:
    base: dict[str, Any] = {
        "case_type": "cargo_duplicado",
        "customer_reply": "Revisé tu caso.",
        "reasoning_summary": "Resumen.",
        "action": None,
        "citations": ["aclaraciones#cuando-procede-una-aclaracion"],
        "no_support": False,
    }
    return json.dumps({**base, **overrides}, ensure_ascii=False)


def context(customer_id: str = "cus_004", message: str = "Me cobraron dos veces") -> CaseContext:
    return CaseContext(case_id="case_test", customer_id=customer_id, as_of=AS_OF, message=message)


def mcp_tool_results(customer_id: str, calls: list[tuple[str, dict[str, Any]]]) -> list[ToolResult]:
    """Real tool results from an in-memory MCP session bound to the customer."""
    server = create_server(JsonCoreRepository(), customer_id)

    async def main() -> list[ToolResult]:
        results: list[ToolResult] = []
        async with Client(server) as client:
            for name, args in calls:
                result = await client.call_tool(name, args)
                block = result.content[0]
                assert isinstance(block, TextContent)
                if not result.is_error:
                    results.append(ToolResult(name=name, args=args, payload=json.loads(block.text)))
        return results

    return anyio.run(main)
