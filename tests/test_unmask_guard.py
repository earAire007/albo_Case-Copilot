"""Spec 02 — textual guard for unmask (complements the import-linter contract).

import-linter misses dynamic imports (importlib) and does not cover scripts/ or data/.
Any `unmask` token outside its own module (and tests) fails here.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCANNED = ("backend", "mcp_server", "scripts", "data")
# Spec 05 adds the executor module here.
ALLOWED = {Path("backend/security/unmask.py")}
TOKEN = re.compile(r"\bunmask\b")


def test_unmask_token_only_in_allowed_modules():
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{n}"
        for top in SCANNED
        for path in sorted((REPO_ROOT / top).rglob("*.py"))
        if path.relative_to(REPO_ROOT) not in ALLOWED
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if TOKEN.search(line)
    ]
    assert not offenders, offenders
