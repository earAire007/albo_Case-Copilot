"""Detector of unmasked sensitive identifiers in free text (logs, traces, model I/O).

Base for `mask()` (spec 02). Findings carry kind and position only, never the value,
so reporting a leak cannot leak it again. Error direction is deliberate: when unsure,
over-detect.

- CLABE / card: digit runs of 13-19 digits that pass their checksum (CLABE check
  digit for 18 digits, otherwise Luhn). Groups split by a single space or hyphen are
  joined first (every group >= 3 digits except the last, so 4-4-4-4 cards and 3-3-11-1
  CLABEs match) and checked only if the joined length is 13-19.
- long_number: any contiguous run of 20+ digits. No sliding windows: in long runs
  some window passes a checksum by chance, so the whole run is reported instead.
- RFC / CURP: format only, no check digit. Errors are false positives, acceptable.
- SPEI tracking key (`CC` + 18 digits, dataset format) is NOT sensitive: it is needed
  to query SPEI status and resend the CEP. Exact-format exception only; a generic
  "letters next to digits" rule would let a CLABE glued to text through.
"""

import re
from dataclasses import dataclass
from typing import Literal

from backend.domain.validators import CURP_RE, RFC_RE, clabe_is_valid, luhn_is_valid

Kind = Literal["clabe", "card", "long_number", "rfc", "curp"]

CARD_LENGTHS = range(13, 20)
LONG_NUMBER_MIN = 20

_DIGIT_RUN = re.compile(r"(?<!\d)\d+(?!\d)")
_GROUPED = re.compile(r"(?<!\d)\d{3,}(?:[ -]\d{3,})*[ -]\d+(?!\d)")
TRACKING_KEY_RE = re.compile(r"(?<![A-Za-z0-9])CC(\d{18})(?!\d)")
_CURP = re.compile(rf"(?<![A-Z0-9]){CURP_RE.pattern}(?![A-Z0-9])")
_RFC = re.compile(rf"(?<![A-ZÑ&0-9]){RFC_RE.pattern}(?![A-Z0-9])")


@dataclass(frozen=True)
class Finding:
    kind: Kind
    start: int
    end: int


def _classify(digits: str) -> Kind | None:
    if len(digits) == 18 and clabe_is_valid(digits):
        return "clabe"
    if len(digits) in CARD_LENGTHS and luhn_is_valid(digits):
        return "card"
    return None


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < e and s < end for s, e in spans)


def _numeric_findings(text: str) -> list[Finding]:
    tracking = [m.span(1) for m in TRACKING_KEY_RE.finditer(text)]
    findings: list[Finding] = []
    for m in _DIGIT_RUN.finditer(text):
        if m.span() in tracking:
            continue
        if len(m.group()) >= LONG_NUMBER_MIN:
            findings.append(Finding("long_number", m.start(), m.end()))
        elif kind := _classify(m.group()):
            findings.append(Finding(kind, m.start(), m.end()))
    taken = [(f.start, f.end) for f in findings]
    for m in _GROUPED.finditer(text):
        if _overlaps(m.start(), m.end(), taken):
            continue
        joined = re.sub(r"[ -]", "", m.group())
        if len(joined) in CARD_LENGTHS and (kind := _classify(joined)):
            findings.append(Finding(kind, m.start(), m.end()))
    return findings


def find_sensitive(text: str) -> list[Finding]:
    findings = _numeric_findings(text)
    curp_spans = []
    for m in _CURP.finditer(text):
        findings.append(Finding("curp", m.start(), m.end()))
        curp_spans.append((m.start(), m.end()))
    for m in _RFC.finditer(text):
        # A CURP starts with the same 10 chars as the RFC stem; don't double-report it.
        if not any(s <= m.start() < e for s, e in curp_spans):
            findings.append(Finding("rfc", m.start(), m.end()))
    return sorted(findings, key=lambda f: f.start)
