"""Spec 07 (ajuste tras clon limpio) — motivo del estado en la vista del caso: catálogo fijo
para operaciones, elegido por la traza, sin texto de la traza ni mensajes de excepción; y
aviso al arrancar sin credenciales del modelo."""

import logging
from datetime import datetime

import anyio
import pytest

from backend.agent.model import ModelRequestError, TransientModelError
from backend.app.api import _production_app
from backend.approval import service
from backend.llm.anthropic_client import AnthropicModel, LlmSettings
from backend.orchestrator.loop import LoopConfig
from backend.store.store import Store
from backend.worker.worker import run_once

from .agent_helpers import output_json
from .spec06_helpers import LATER, RECEIVED, REPO, case_with_proposal, client_for, post_ticket
from .test_anthropic_adapter import FakeMessages, NoCredentialsMessages, fake_client
from .test_loop import FakeModel, call, final, step

CLABE = "646180522488216773"
FAST = LoopConfig(price_input_per_mtok=4.0, price_output_per_mtok=20.0, base_delay_s=0.0)

CONFIG_ERROR = (
    "El servicio del modelo no está configurado o no aceptó la credencial; atiende el caso a mano."
)
UNAVAILABLE = (
    "El modelo no respondió después de varios reintentos; "
    "atiende el caso a mano o reprocésalo más tarde."
)
PROVIDER = "El proveedor del modelo rechazó la solicitud; atiende el caso a mano."
BUDGET = "El agente agotó su presupuesto sin llegar a una respuesta."
REFUSAL = "El modelo se negó a responder este caso."
TRUNCATED = "La respuesta del modelo quedó incompleta."
WORKER = "El procesamiento falló varias veces por un error interno."
EXECUTION = (
    "La aprobación quedó registrada, pero la ejecución no se completó; reintenta la ejecución."
)
GENERIC = "El caso necesita revisión humana."


def _work(store: Store, model: FakeModel, now: datetime = RECEIVED) -> None:
    async def main() -> None:
        await run_once(store, model, FAST, repo=REPO, now=lambda: now)

    anyio.run(main)


def _view(model: FakeModel, runs: int = 1) -> dict:
    store = Store(":memory:")
    client = client_for(store)
    case_id = post_ticket(client).json()["case_id"]
    for _ in range(runs):
        _work(store, model)
    return client.get(f"/cases/{case_id}").json()


LEAK = output_json(customer_reply=f"Tu CLABE es {CLABE}", citations=[], no_support=True)
SPIN = [step(call("get_customer", {}, f"t{i}")) for i in range(FAST.max_tool_steps + 1)]


@pytest.mark.parametrize(
    ("script", "runs", "expected"),
    [
        ([ModelRequestError("config")], 1, CONFIG_ERROR),
        ([TransientModelError("server")] * (FAST.max_retries + 1), 1, UNAVAILABLE),
        ([ModelRequestError("bad_request")], 1, PROVIDER),
        (SPIN, 1, BUDGET),
        ([final(tokens=(FAST.max_case_tokens, 1))], 1, BUDGET),
        ([final(stop="refusal")], 1, REFUSAL),
        ([final(stop="max_tokens")], 1, TRUNCATED),
        ([RuntimeError(f"core caído {CLABE}")] * 2, 2, WORKER),
    ],
)
def test_status_reason_catalog(script, runs, expected):
    view = _view(FakeModel(*script), runs)
    assert view["status"] == "requires_human"
    assert view["status_reason"] == expected
    assert CLABE not in str(view)


def test_status_reason_lists_rejections_in_ops_language():
    view = _view(FakeModel(final(LEAK)))
    assert view["status"] == "requires_human"
    reason = view["status_reason"]
    assert reason.startswith("La respuesta del agente no pasó las validaciones: ")
    assert "datos sensibles" in reason
    assert CLABE not in reason and "digits" not in reason, "sin texto ni nombres internos"


def test_status_reason_uses_only_the_last_model_step_rejections():
    """A format rejection repaired earlier does not show up next to the final one."""
    view = _view(FakeModel(final("esto no es json"), final(LEAK)))
    assert "formato" not in view["status_reason"] and "datos sensibles" in view["status_reason"]


def test_status_reason_for_failed_execution(monkeypatch):
    store = Store(":memory:")
    client = client_for(store)
    case_id, pid = case_with_proposal(store, client, "k-exec")

    def boom(store, proposal_id):
        raise RuntimeError(f"core caído {CLABE}")

    monkeypatch.setattr(service, "execute", boom)
    with pytest.raises(RuntimeError):
        service.approve(store, pid, "ops")
    view = client.get(f"/cases/{case_id}").json()
    assert view["status"] == "execution_failed" and view["status_reason"] == EXECUTION
    assert CLABE not in str(view)


def test_status_reason_without_signal_is_generic():
    """A stuck job out of attempts leaves no trace: generic reason."""
    store = Store(":memory:")
    client = client_for(store)
    case_id = post_ticket(client).json()["case_id"]
    store.claim_job(now=RECEIVED)
    store.requeue_stuck_jobs(older_than=LATER, max_attempts=1)
    view = client.get(f"/cases/{case_id}").json()
    assert view["status"] == "requires_human" and view["status_reason"] == GENERIC


def test_status_reason_is_null_outside_human_states():
    assert _view(FakeModel(final()))["status_reason"] is None  # answered
    store = Store(":memory:")
    client = client_for(store)
    case_id, _ = case_with_proposal(store, client, "k-pend")
    assert client.get(f"/cases/{case_id}").json()["status_reason"] is None
    assert client.get("/cases").json()[0]["status_reason"] is None


def test_startup_warns_without_credentials(caplog):
    unconfigured = AnthropicModel(
        LlmSettings(), client=fake_client(NoCredentialsMessages(), api_key=None)
    )
    with caplog.at_level(logging.WARNING):
        _production_app(store=Store(":memory:"), model=unconfigured)
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("revisión humana" in m for m in warnings), warnings

    caplog.clear()
    configured = AnthropicModel(LlmSettings(), client=fake_client(FakeMessages()))
    with caplog.at_level(logging.WARNING):
        _production_app(store=Store(":memory:"), model=configured)
    assert not [r for r in caplog.records if "revisión humana" in r.getMessage()]
