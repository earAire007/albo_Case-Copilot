"""mask(): the single masking step every MCP response goes through (spec 02, invariant 4).

- CLABE and card -> `****` + last 4 digits (the customer can recognize "terminación 5678").
- RFC, CURP and long_number -> fully replaced by a type tag (`[RFC]`, `[CURP]`,
  `[LONG_NUMBER]`): their last characters don't identify anything to the customer.
- Known sensitive fields are masked by name; every other string goes through
  `find_sensitive` (spec 01b) with the same rules. A SPEI tracking key (`CC` + 18
  digits) passes untouched because the detector excludes that exact format; there is no
  exemption by field name, so a CLABE placed in `tracking_key` is still masked.

Integers with 13+ digits are treated as text and go through the detector (a CLABE or
card stored as a number); shorter ints (amounts) pass untouched.
Over-masking is accepted: a 13–19 digit int that passes Luhn by chance (e.g. a
millisecond timestamp) comes out as `****1234`, a string.

Pure function: returns a new structure, never mutates the input.
"""

from typing import overload

from backend.domain.sensitive import Kind, find_sensitive

type Json = dict[str, Json] | list[Json] | str | int | float | bool | None

SENSITIVE_FIELDS: dict[str, Kind] = {
    "clabe": "clabe",
    "counterparty_clabe": "clabe",
    "card_number": "card",
    "rfc": "rfc",
    "curp": "curp",
}
_LAST4_KINDS: frozenset[Kind] = frozenset({"clabe", "card"})
LONG_INT_DIGITS = 13


def _render(kind: Kind, original: str) -> str:
    if kind in _LAST4_KINDS:
        digits = "".join(ch for ch in original if ch.isdigit())
        return "****" + digits[-4:]
    return f"[{kind.upper()}]"


def mask_text(text: str) -> str:
    out = text
    for finding in sorted(find_sensitive(text), key=lambda f: f.start, reverse=True):
        out = (
            out[: finding.start]
            + _render(finding.kind, text[finding.start : finding.end])
            + out[finding.end :]
        )
    return out


@overload
def mask(value: dict[str, Json], field: str | None = None) -> dict[str, Json]: ...
@overload
def mask(value: Json, field: str | None = None) -> Json: ...
def mask(value: Json, field: str | None = None) -> Json:
    if isinstance(value, dict):
        return {key: mask(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [mask(item, field) for item in value]
    if isinstance(value, int) and not isinstance(value, bool):
        text = str(value)
        if len(text.lstrip("-")) < LONG_INT_DIGITS:
            return value
        masked = mask_text(text)
        return value if masked == text else masked
    if not isinstance(value, str):
        return value
    if field is not None and field in SENSITIVE_FIELDS:
        return _render(SENSITIVE_FIELDS[field], value)
    return mask_text(value)
