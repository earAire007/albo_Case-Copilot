"""Spec 05b — adaptador del proveedor: la petición que arma, sin red (cliente del SDK falso)."""

from types import SimpleNamespace
from typing import Any

import anthropic
import anyio
import httpx2
import pytest

from backend.agent.model import (
    ModelRequestError,
    OpaqueBlock,
    TextBlock,
    ToolCall,
    ToolSpec,
    TransientModelError,
)
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


def _status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    response = httpx2.Response(status, request=httpx2.Request("POST", "https://api.example"))
    return cls("error", response=response, body=None)


class RaisingMessages:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def create(self, **kwargs: Any) -> Any:
        raise self.exc


_REQUEST = httpx2.Request("POST", "https://api.example")


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_status_error(anthropic.BadRequestError, 400), (ModelRequestError, "bad_request")),
        (_status_error(anthropic.AuthenticationError, 401), (ModelRequestError, "auth")),
        (_status_error(anthropic.PermissionDeniedError, 403), (ModelRequestError, "auth")),
        (_status_error(anthropic.NotFoundError, 404), (ModelRequestError, "not_found")),
        (_status_error(anthropic.UnprocessableEntityError, 422), (ModelRequestError, "request")),
        (_status_error(anthropic.RateLimitError, 429), (TransientModelError, "rate_limit")),
        (_status_error(anthropic.InternalServerError, 500), (TransientModelError, "server")),
        (anthropic.APITimeoutError(request=_REQUEST), (TransientModelError, "timeout")),
        (anthropic.APIConnectionError(request=_REQUEST), (TransientModelError, "connection")),
    ],
)
def test_adapter_maps_provider_errors(exc, expected):
    model = AnthropicModel(SETTINGS, client=SimpleNamespace(messages=RaisingMessages(exc)))
    cls, kind = expected
    with pytest.raises(cls) as info:
        anyio.run(model.step, "s", [{"role": "user", "content": "hola"}], [])
    assert info.value.kind == kind
