"""Model ports. Spec 05a uses test doubles; spec 05b plugs in the real provider.

Provider-neutral: the adapter in backend/llm maps these to and from the SDK; the agent
and the orchestrator never see SDK types.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol


class ModelClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


# --- Tool-calling port (spec 05b) ---


@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: Mapping[str, Any]


@dataclass(frozen=True)
class OpaqueBlock:
    """A provider block passed back unchanged (e.g. thinking). Never traced."""

    raw: Any


Block = TextBlock | ToolCall | OpaqueBlock


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ModelStep:
    blocks: tuple[Block, ...]
    stop_reason: str
    usage: Usage
    model: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, Any]


class TransientModelError(Exception):
    """Retryable provider failure, already classified by the adapter."""

    def __init__(self, kind: Literal["rate_limit", "timeout", "server", "connection"]) -> None:
        super().__init__(kind)
        self.kind = kind


class ModelRequestError(Exception):
    """Non-retryable provider failure (4xx): the case goes to a human, never retried."""

    def __init__(self, kind: Literal["bad_request", "auth", "not_found", "request"]) -> None:
        super().__init__(kind)
        self.kind = kind


class ToolCallingModel(Protocol):
    async def step(
        self, system: str, messages: list[dict[str, Any]], tools: Sequence[ToolSpec]
    ) -> ModelStep: ...
