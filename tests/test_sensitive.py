"""Spec 01b — AC2, AC3: detector de datos sensibles y fixture global de logs."""

from pathlib import Path

import pytest

from backend.domain.sensitive import find_sensitive
from backend.domain.validators import clabe_is_valid, luhn_is_valid

REPO_ROOT = Path(__file__).resolve().parent.parent
INVALID_18_DIGITS = "646180000000000001"


def test_detector_finds_every_dataset_identifier(raw_customers):
    for c in raw_customers:
        for field, kind in (
            ("clabe", "clabe"),
            ("card_number", "card"),
            ("rfc", "rfc"),
            ("curp", "curp"),
        ):
            text = f"cliente {c['id']} dato={c[field]} fin"
            kinds = {f.kind for f in find_sensitive(text)}
            assert kind in kinds, (c["id"], field)


def test_detector_ignores_masked_and_invalid_numbers():
    assert not clabe_is_valid(INVALID_18_DIGITS) and not luhn_is_valid(INVALID_18_DIGITS)
    for text in ("CLABE ****1234", "tarjeta **** **** **** 4242", INVALID_18_DIGITS, "cus_001"):
        assert find_sensitive(text) == [], text


def test_findings_never_carry_the_value(raw_customers):
    clabe = raw_customers[0]["clabe"]
    (finding,) = [f for f in find_sensitive(f"x {clabe}") if f.kind == "clabe"]
    assert (finding.start, finding.end) == (2, 20)
    assert clabe not in repr(finding)


def _run_inner(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, payload: str):
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    pytester.makepyfile(
        test_inner=f"""
import logging

def test_logs_payload():
    logging.getLogger("app.inner").info("payload=%s", {payload!r})
"""
    )
    # Subprocess: the outer autouse fixture must not see the inner session's logs.
    return pytester.runpytest_subprocess("-p", "tests.sensitive_logs", "-q")


@pytest.mark.parametrize("field", ["clabe", "card_number", "rfc", "curp"])
def test_fixture_fails_on_raw_identifier(pytester, monkeypatch, raw_customers, field):
    result = _run_inner(pytester, monkeypatch, raw_customers[0][field])
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*datos sensibles sin enmascarar*"])


@pytest.mark.parametrize("payload", ["CLABE ****1234", INVALID_18_DIGITS, "txn_0001"])
def test_fixture_passes_on_masked_or_invalid(pytester, monkeypatch, payload):
    result = _run_inner(pytester, monkeypatch, payload)
    assert result.ret == 0, result.stdout.str()
