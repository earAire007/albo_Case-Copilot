"""Heuristic prompt-injection detector (spec 05b). A signal for metrics, never the
guarantee (invariant 5): it decides nothing; the validators of spec 05a do.

Returns pattern names, never the matched text, so the signal itself carries no data.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

Vector = Literal["customer_message", "policy_chunk", "tool_result"]

_AGENT = r"(asistentes|agentes|modelos)"
_GATE = r"(aprobaci\w+|validaci\w+|verificaci\w+|approval|verification)"
_MONEY = r"(reembols\w+|deposit\w+|transfi\w+|refund|transfer)"
_DEST = r"(clabe|cuenta que indique|a la cuenta|account)"

_PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(
        r"\b(ignora\w*|olvida\w*|ignore|disregard)\b.{0,30}"
        r"\b(instrucciones|reglas|instructions|rules)\b"
    ),
    "role_override": re.compile(
        r"\b(eres un (sistema|asistente|agente)|you are (now )?(an? )?(system|assistant|agent))\b"
    ),
    "addressed_to_agent": re.compile(
        rf"\b(nota para (los )?{_AGENT}|agente\s*:|assistant\s*:|note to (the )?(assistant|ai))"
    ),
    "skip_approval": re.compile(rf"\b(sin esperar|omit\w*|salt\w*|without)\b.{{0,20}}\b{_GATE}\b"),
    "money_command": re.compile(rf"\b{_MONEY}\b.{{0,40}}\b{_DEST}\b"),
    "reveal_data": re.compile(
        r"\b(muestra|incluye|revela|show|reveal)\b.{0,40}\b(completos?|full)\b"
    ),
}


@dataclass(frozen=True)
class InjectionSignal:
    vector: Vector
    detected: bool
    patterns: tuple[str, ...]


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def scan(vector: Vector, text: str) -> InjectionSignal:
    folded = _normalize(text)
    hits = tuple(name for name, pattern in _PATTERNS.items() if pattern.search(folded))
    return InjectionSignal(vector=vector, detected=bool(hits), patterns=hits)
