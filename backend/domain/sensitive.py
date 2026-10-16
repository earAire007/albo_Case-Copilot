"""Detector of unmasked sensitive identifiers in free text (logs, traces).

Findings carry kind and position only, never the value, so reporting a leak cannot
leak it again. Numeric candidates must pass their checksum (CLABE check digit or
Luhn) to cut false positives on ids and tracking keys.
"""

import re
from dataclasses import dataclass
from typing import Literal

from backend.domain.validators import CURP_RE, RFC_RE, clabe_is_valid, luhn_is_valid

Kind = Literal["clabe", "card", "rfc", "curp"]

_DIGIT_RUN = re.compile(r"(?<!\d)\d{13,19}(?!\d)")
_CURP = re.compile(rf"(?<![A-Z0-9]){CURP_RE.pattern}(?![A-Z0-9])")
_RFC = re.compile(rf"(?<![A-ZÑ&0-9]){RFC_RE.pattern}(?![A-Z0-9])")


@dataclass(frozen=True)
class Finding:
    kind: Kind
    start: int
    end: int


def find_sensitive(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for m in _DIGIT_RUN.finditer(text):
        digits = m.group()
        if len(digits) == 18 and clabe_is_valid(digits):
            findings.append(Finding("clabe", m.start(), m.end()))
        elif luhn_is_valid(digits):
            findings.append(Finding("card", m.start(), m.end()))
    curp_spans = []
    for m in _CURP.finditer(text):
        findings.append(Finding("curp", m.start(), m.end()))
        curp_spans.append((m.start(), m.end()))
    for m in _RFC.finditer(text):
        # A CURP starts with the same 10 chars as the RFC stem; don't double-report it.
        if not any(s <= m.start() < e for s, e in curp_spans):
            findings.append(Finding("rfc", m.start(), m.end()))
    return sorted(findings, key=lambda f: f.start)
