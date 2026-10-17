"""Digit-run rule shared by the agent's output validators (spec 05a) and the human reply
edit (spec 07). Neutral module: backend.approval cannot import backend.agent.

A run of 13+ digits is refused unless it is a SPEI tracking key that this case's tools
actually returned. The exemption is by provenance, never by format: `CC` + a CLABE has
the tracking-key format and is still refused.

Text is normalized first (NFKC, invisible format characters removed) and well-formed
times (HH:MM[:SS]) are dropped, so ":" can count as a separator without rejecting
"2026-07-18 14:32:10". Residual risk, accepted: digits split by words of 4+ letters
("646180 luego 522488216773") or disguised as a sequence of times ("6:46 18:01 9 ...")
pass; deterministic rules cannot chase every obfuscation, and the last defense is the
human approver.
"""

import re
import unicodedata
from collections.abc import Collection, Iterable, Mapping

from backend.domain.sensitive import TRACKING_KEY_RE

# 13+ digits joined by any run of characters that are neither letters nor digits (commas,
# colons, asterisks, dashes, NBSP, newlines...), or by a word of 1-3 letters with or
# without spaces ("646180 y 522488216773", "646180x522488216773"). No checksum: an
# invented number probably would not pass one, and the 01b detector would miss it.
# False positives go the safe way: the case goes to a human.
SEPARATOR = r"(?:[^\w]|_)+"
_SEP = rf"(?:{SEPARATOR}|\s*[^\W\d_]{{1,3}}\s*)?"
_TIME = re.compile(r"(?<![\d:])(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?![\d:])")
DIGIT_RUN = re.compile(rf"\d(?:{_SEP}\d){{12,}}")


def normalize(text: str) -> str:
    """NFKC (full-width digits, compatibility forms) without format characters (ZWSP,
    soft hyphen and other Unicode category Cf)."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


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
    text = normalize(text)
    for key in exempt:
        text = text.replace(key, "")
    text = _TIME.sub(" ", text)
    return DIGIT_RUN.search(text) is not None
