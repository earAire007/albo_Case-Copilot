"""Anthropic adapter for the tool-calling port (spec 05b).

- Model, effort, max_tokens and timeout come from the environment (.env).
- `max_retries=0`: retries are ours (orchestrator), so each one is traced and the sleep
  can be injected in tests. Retryable SDK errors become TransientModelError.
- No server-side fallbacks on refusal (see DESIGN.md, trade-offs).
- tool_choice "auto": the default model rejects forced tool choice.
- Structured output (output_config.format, JSON schema of AgentOutput): the final answer
  is schema-valid JSON. Documented as compatible with tools and thinking on
  claude-opus-5-5. The validators and Pydantic still run on every output.
- Thinking blocks are returned as OpaqueBlock and passed back unchanged.
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

import anthropic
from anthropic.types import MessageParam, OutputConfigParam, ToolParam

from backend.agent.model import (
    Block,
    ModelRequestError,
    ModelStep,
    OpaqueBlock,
    TextBlock,
    ToolCall,
    ToolSpec,
    TransientModelError,
    Usage,
)
from backend.agent.output import output_json_schema

DEFAULT_MODEL = "claude-opus-5-5"
Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class LlmSettings:
    model: str = DEFAULT_MODEL
    effort: Effort = "medium"
    max_tokens: int = 16_000
    timeout_s: float = 120.0

    @classmethod
    def from_env(cls) -> "LlmSettings":
        return cls(
            model=os.environ.get("MODEL", DEFAULT_MODEL),
            effort=cast(Effort, os.environ.get("EFFORT", "medium")),
            max_tokens=int(os.environ.get("MAX_OUTPUT_TOKENS", "16000")),
            timeout_s=float(os.environ.get("LLM_TIMEOUT_S", "120")),
        )


def _to_param(block: Any) -> Any:
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    if isinstance(block, ToolCall):
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input)}
    if isinstance(block, OpaqueBlock):
        return block.raw
    return block


def _to_message(message: dict[str, Any]) -> MessageParam:
    content = message["content"]
    if isinstance(content, list):
        content = [_to_param(b) for b in content]  # pyright: ignore[reportUnknownVariableType]
    return cast(MessageParam, {"role": message["role"], "content": content})


def _from_block(block: Any) -> Block:
    if block.type == "text":
        return TextBlock(block.text)
    if block.type == "tool_use":
        return ToolCall(id=block.id, name=block.name, input=dict(block.input))
    return OpaqueBlock(block)


class AnthropicModel:
    def __init__(self, settings: LlmSettings, client: Any = None) -> None:
        self.settings = settings
        self.client = client or anthropic.AsyncAnthropic(max_retries=0, timeout=settings.timeout_s)

    async def step(
        self, system: str, messages: list[dict[str, Any]], tools: Sequence[ToolSpec]
    ) -> ModelStep:
        tool_params: list[ToolParam] = [
            {"name": t.name, "description": t.description, "input_schema": dict(t.input_schema)}
            for t in tools
        ]
        output_config = cast(
            OutputConfigParam,
            {
                "effort": self.settings.effort,
                "format": {"type": "json_schema", "schema": output_json_schema()},
            },
        )
        try:
            response = await self.client.messages.create(
                model=self.settings.model,
                max_tokens=self.settings.max_tokens,
                system=system,
                messages=[_to_message(m) for m in messages],
                tools=tool_params,
                tool_choice={"type": "auto"},
                output_config=output_config,
            )
        except anthropic.RateLimitError as exc:
            raise TransientModelError("rate_limit") from exc
        except anthropic.APITimeoutError as exc:
            raise TransientModelError("timeout") from exc
        except anthropic.APIConnectionError as exc:
            raise TransientModelError("connection") from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise ModelRequestError("auth") from exc
        except anthropic.BadRequestError as exc:
            raise ModelRequestError("bad_request") from exc
        except anthropic.NotFoundError as exc:
            raise ModelRequestError("not_found") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise TransientModelError("server") from exc
            raise ModelRequestError("request") from exc
        return ModelStep(
            blocks=tuple(_from_block(b) for b in response.content),
            stop_reason=response.stop_reason or "end_turn",
            usage=Usage(response.usage.input_tokens, response.usage.output_tokens),
            model=response.model,
        )
