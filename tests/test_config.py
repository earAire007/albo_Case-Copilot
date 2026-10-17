"""Configuración desde el entorno: vacío = ausente, inválido = error que nombra la variable,
y el `.env.example` versionado construye la configuración de producción sin errores
(hallazgo del clon limpio: `LLM_TIMEOUT_S=` vacía tumbaba el arranque en Docker)."""

import logging
import re
from pathlib import Path

import pytest

from backend.app.api import _production_app
from backend.config import ConfigError
from backend.llm.anthropic_client import LlmSettings
from backend.orchestrator.loop import LoopConfig
from backend.store.store import Store

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"
NUMERIC = {
    "MAX_OUTPUT_TOKENS": "un entero",
    "LLM_TIMEOUT_S": "un número",
    "PRICE_INPUT_PER_MTOK": "un número",
    "PRICE_OUTPUT_PER_MTOK": "un número",
    "MAX_TOOL_STEPS": "un entero",
    "MAX_CASE_TOKENS": "un entero",
}
ALL = [*NUMERIC, "MODEL", "EFFORT", "CONSOLE_DIST"]


def _example() -> list[tuple[int, str, str]]:
    """(line index, name, value) per assignment, with compose env_file semantics."""
    entries = []
    for i, line in enumerate(ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, _, value = stripped.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        entries.append((i, name.strip(), value))
    return entries


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_variables_take_the_default(monkeypatch, value):
    for name in ALL:
        monkeypatch.setenv(name, value)
    assert LlmSettings.from_env() == LlmSettings()
    loop = LoopConfig.from_env()
    assert (loop.price_input_per_mtok, loop.price_output_per_mtok) == (4.0, 20.0)
    assert (loop.max_tool_steps, loop.max_case_tokens) == (6, 30_000)


@pytest.mark.parametrize("name", [*NUMERIC, "EFFORT"])
def test_invalid_value_names_the_variable_not_the_value(monkeypatch, name):
    monkeypatch.setenv(name, "sk-ant-pegada-por-error")
    with pytest.raises(ConfigError) as info:
        LlmSettings.from_env()
        LoopConfig.from_env()
    message = str(info.value)
    assert message.startswith(f"{name}: valor inválido")
    assert "sk-ant" not in message, "nunca el valor: podría ser una key mal pegada"


def test_invalid_config_stops_startup_without_traceback(monkeypatch, caplog):
    monkeypatch.setenv("LLM_TIMEOUT_S", "dos minutos")
    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as info:
        _production_app(store=Store(":memory:"))
    assert info.value.code == 1
    (record,) = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert "LLM_TIMEOUT_S" in record.getMessage() and record.exc_info is None


def test_env_example_builds_production_config(monkeypatch):
    """The versioned example, as `cp .env.example .env` leaves it, must start the app."""
    entries = _example()
    assert entries, ".env.example sin variables"
    for _, name, value in entries:
        monkeypatch.setenv(name, value)
    LlmSettings.from_env()
    LoopConfig.from_env()
    _production_app(store=Store(":memory:"))  # raises SystemExit on invalid config


def test_env_example_has_nothing_shaped_like_a_secret():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-|sk-[A-Za-z0-9_-]{16,}", text), "parece una API key"
    key = {name: value for _, name, value in _example()}["ANTHROPIC_API_KEY"]
    assert key == "", "ANTHROPIC_API_KEY va vacía en el ejemplo"


def test_env_example_comments_every_variable():
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    uncommented = [
        name for i, name, _ in _example() if i == 0 or not lines[i - 1].strip().startswith("#")
    ]
    assert uncommented == [], f"sin comentario encima: {uncommented}"
