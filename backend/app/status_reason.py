"""Why a case needs a person (spec 07, clean-clone adjustment).

A fixed catalog in Spanish for operations, chosen by the last signal in the trace. Only
trace step names, stop reasons and validator names are read: never trace text or
exception messages, so nothing sensitive or raw can reach the console.
"""

from collections.abc import Sequence
from typing import Any

EXECUTION_FAILED = (
    "La aprobación quedó registrada, pero la ejecución no se completó; reintenta la ejecución."
)
GENERIC = "El caso necesita revisión humana."
WORKER_ERROR = "El procesamiento falló varias veces por un error interno."
REJECTED = "La respuesta del agente no pasó las validaciones: "

_BUDGET = "El agente agotó su presupuesto sin llegar a una respuesta."
STOPS = {
    "config_error": (
        "El servicio del modelo no está configurado o no aceptó la credencial; "
        "atiende el caso a mano."
    ),
    "provider_unavailable": (
        "El modelo no respondió después de varios reintentos; "
        "atiende el caso a mano o reprocésalo más tarde."
    ),
    "provider_error": "El proveedor del modelo rechazó la solicitud; atiende el caso a mano.",
    "budget_steps": _BUDGET,
    "budget_tokens": _BUDGET,
    "refusal": "El modelo se negó a responder este caso.",
    "max_tokens": "La respuesta del modelo quedó incompleta.",
}
VALIDATORS = {
    "schema": "formato de la respuesta",
    "no_support": "sustento en las políticas",
    "citations": "citas de políticas",
    "facts": "datos que no coinciden con las herramientas",
    "digits": "datos sensibles en la respuesta",
    "action": "acción no permitida para este caso",
}
_SIGNALS = frozenset({"stop", "rejection", "worker_error"})
_MODEL_STEPS = frozenset({"model_step", "model_output"})  # 05b loop and 05a turn


def status_reason(status: str, traces: Sequence[dict[str, Any]]) -> str | None:
    if status == "execution_failed":
        return EXECUTION_FAILED
    if status != "requires_human":
        return None
    signals = [t for t in traces if t["step"] in _SIGNALS]
    if not signals:
        return GENERIC  # e.g. a stuck job out of attempts
    last = signals[-1]
    if last["step"] == "stop":
        return STOPS.get(str(last["payload"].get("reason")), GENERIC)
    if last["step"] == "worker_error":
        return WORKER_ERROR
    return REJECTED + ", ".join(_last_rejections(traces)) + "."


def _last_rejections(traces: Sequence[dict[str, Any]]) -> list[str]:
    """Rejections of the last model step only: a repaired format failure does not count."""
    start = max((i for i, t in enumerate(traces) if t["step"] in _MODEL_STEPS), default=-1)
    labels: list[str] = []
    for trace in traces[start + 1 :]:
        if trace["step"] == "rejection":
            label = VALIDATORS.get(str(trace["validator"]), "otra validación")
            if label not in labels:
                labels.append(label)
    return labels
