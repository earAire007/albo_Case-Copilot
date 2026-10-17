"""Digit-run rule shared by the agent's output validators (spec 05a) and the human reply
edit (spec 07). Neutral module: backend.approval cannot import backend.agent.

A run of 13+ digits is refused unless it is a SPEI tracking key that this case's tools
actually returned. The exemption is by provenance, never by format: `CC` + a CLABE has
the tracking-key format and is still refused.
"""

import re
from collections.abc import Collection, Iterable, Mapping

from backend.domain.sensitive import TRACKING_KEY_RE

# 13+ digits joined by any mix of whitespace (incl. NBSP and newlines), dots, hyphens,
# slashes or underscores, or split by a short word ("646180 y 522488216773"). No checksum:
# an invented number probably would not pass one, and the 01b detector would miss it.
_SEP = r"(?:[\s.\-/_]+|\s+[^\W\d_]{1,3}\s+)?"
DIGIT_RUN = re.compile(rf"\d(?:{_SEP}\d){{12,}}")


def walk(value: object) -> list[Mapping[str, object]]:
    """Every mapping nested in a JSON-like value."""
    found: list[Mapping[str, object]] = []
    if isinstance(value, Mapping):
        mapping: Mapping[str, object] = value  # pyright: ignore[reportUnknownVariableType]
        found.append(mapping)
        for item in mapping.values():
            found.extend(walk(item))
    elif isinstance(value, list):
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            found.extend(walk(item))  # pyright: ignore[reportUnknownArgumentType]
    return found


def tracking_keys(payloads: Iterable[object]) -> set[str]:
    """Tracking keys present in `tracking_key` fields of tool payloads."""
    keys: set[str] = set()
    for payload in payloads:
        for node in walk(payload):
            key = node.get("tracking_key")
            if isinstance(key, str) and TRACKING_KEY_RE.fullmatch(key):
                keys.add(key)
    return keys


def has_digit_run(text: str, exempt: Collection[str]) -> bool:
    for key in exempt:
        text = text.replace(key, "")
    return DIGIT_RUN.search(text) is not None
