"""Spec 05b — adaptador del proveedor: la petición que arma, sin red (cliente del SDK falso)."""

from types import SimpleNamespace
from typing import Any

import anyio

from backend.agent.model import OpaqueBlock, TextBlock, ToolCall, ToolSpec
from backend.llm.anthropic_client import AnthropicModel, LlmSettings

SETTINGS = LlmSettings(model="claude-opus-5-5", effort="medium", max_tokens=16000, timeout_s=60.0)


class FakeMessages:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking="", signature="sig"),
                SimpleNamespace(type="text", text="hola"),
                SimpleNamespace(type="tool_use", id="tu_1", name="get_customer", input={}),
            ],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            model="claude-opus-5-5",
        )


def test_adapter_request_has_no_fallbacks_and_auto_tool_choice():
    messages = FakeMessages()
    model = AnthropicModel(SETTINGS, client=SimpleNamespace(messages=messages))
    tool = ToolSpec(name="get_customer", description="d", input_schema={"type": "object"})
    result = anyio.run(model.step, "sistema", [{"role": "user", "content": "hola"}], [tool])

    kw = messages.kwargs
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"] == {"effort": "medium"}
    assert kw["tool_choice"] == {"type": "auto"}
    assert "fallbacks" not in kw and "betas" not in kw
    assert kw["tools"] == [
        {"name": "get_customer", "description": "d", "input_schema": {"type": "object"}}
    ]

    kinds = [type(b) for b in result.blocks]
    assert kinds == [OpaqueBlock, TextBlock, ToolCall]
    assert result.usage.input_tokens == 10 and result.stop_reason == "tool_use"


def test_adapter_client_has_no_sdk_retries():
    model = AnthropicModel(SETTINGS)
    assert model.client.max_retries == 0
