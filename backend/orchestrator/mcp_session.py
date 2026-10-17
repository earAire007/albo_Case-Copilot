"""Adapter from an MCP client session (bound to the case's customer, spec 02) to the
loop's tool-session port."""

from collections.abc import Mapping
from typing import Any

from mcp import Client
from mcp.types import TextContent

from backend.agent.model import ToolSpec


class McpToolSession:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def list_tools(self) -> list[ToolSpec]:
        tools = (await self._client.list_tools()).tools
        return [ToolSpec(t.name, t.description or "", dict(t.input_schema)) for t in tools]

    async def call_tool(self, name: str, args: Mapping[str, Any]) -> tuple[bool, str]:
        result = await self._client.call_tool(name, dict(args))
        text = "".join(b.text for b in result.content if isinstance(b, TextContent))
        return bool(result.is_error), text
