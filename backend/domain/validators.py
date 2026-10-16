"""Format checks for Mexican financial identifiers (CLABE, card PAN, RFC, CURP)."""

import re

CLABE_WEIGHTS = (3, 7, 1)

# Persona física: 4 letters, birth date YYMMDD, 3-char homoclave.
RFC_RE = re.compile(r"[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}")
# 4 letters, birth date, sex, state (2), internal consonants (3), differentiator, check digit.
CURP_RE = re.compile(r"[A-Z]{4}\d{6}[HM][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[A-Z0-9]\d")


def clabe_check_digit(first17: str) -> int:
    total = sum(int(d) * CLABE_WEIGHTS[i % 3] % 10 for i, d in enumerate(first17))
    return (10 - total % 10) % 10


def clabe_is_valid(clabe: str) -> bool:
    return len(clabe) == 18 and clabe.isdigit() and clabe_check_digit(clabe[:17]) == int(clabe[17])


def luhn_is_valid(number: str) -> bool:
    if not number.isdigit() or len(number) < 12:
        return False
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0
