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


LUHN_ONLY_18_DIGITS = "123456789012345671"


def _kinds(text: str) -> list[str]:
    return [f.kind for f in find_sensitive(text)]


def _group(value: str, sizes: tuple[int, ...], sep: str) -> str:
    parts, start = [], 0
    for size in sizes:
        parts.append(value[start : start + size])
        start += size
    return sep.join(parts)


@pytest.mark.parametrize("sep", [" ", "-"])
def test_card_with_separators_is_detected(raw_customers, sep):
    card = raw_customers[0]["card_number"]
    assert _kinds(f"tarjeta {_group(card, (4, 4, 4, 4), sep)} gracias") == ["card"]


def test_clabe_with_spaces_is_detected(raw_customers):
    clabe = raw_customers[0]["clabe"]
    # Canonical layout: bank (3) plaza (3) account (11) check digit (1).
    assert _kinds(f"mi CLABE es {_group(clabe, (3, 3, 11, 1), ' ')}") == ["clabe"]


def test_luhn_valid_non_clabe_18_digits_is_card():
    assert luhn_is_valid(LUHN_ONLY_18_DIGITS) and not clabe_is_valid(LUHN_ONLY_18_DIGITS)
    assert _kinds(LUHN_ONLY_18_DIGITS) == ["card"]


def test_runs_of_20_or_more_digits_are_long_number():
    assert _kinds("ref 12345678901234567890 fin") == ["long_number"]
    assert _kinds("x" + "9" * 40) == ["long_number"]


def test_dataset_tracking_keys_are_not_sensitive(raw_transactions):
    keys = [t["tracking_key"] for t in raw_transactions if t.get("tracking_key")]
    # Some keys' 18 digits pass a checksum by chance: the exception must hold for those.
    assert any(clabe_is_valid(k[2:]) or luhn_is_valid(k[2:]) for k in keys)
    for key in keys:
        assert find_sensitive(f"clave de rastreo {key}") == [], key


def test_clabe_glued_to_text_is_detected(raw_customers):
    assert _kinds(f"clabe{raw_customers[0]['clabe']}") == ["clabe"]


@pytest.mark.parametrize("text", ["1200 3456", "monto 1 200 000", "2026-10-16", "55 1234 5678"])
def test_separated_numbers_without_valid_length_are_ignored(text):
    assert find_sensitive(text) == []


def _run_inner(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    body: str,
) -> pytest.RunResult:
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    pytester.makepyfile(
        test_inner=f"""
import logging
import sys

def test_inner():
    {body}
"""
    )
    # Subprocess: the outer sensors must not see the inner session's logs.
    result = pytester.runpytest_subprocess("-p", "tests.sensitive_logs", "-q")
    # pytester echoes the inner output (which leaks on purpose) to this test's stdout;
    # this test owns that output and asserts on it, so consume it.
    capsys.readouterr()
    return result


@pytest.mark.parametrize("field", ["clabe", "card_number", "rfc", "curp"])
def test_fixture_fails_on_raw_identifier(pytester, monkeypatch, capsys, raw_customers, field):
    value = raw_customers[0][field]
    body = f'logging.getLogger("app.inner").info("payload=%s", {value!r})'
    result = _run_inner(pytester, monkeypatch, capsys, body)
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*datos sensibles sin enmascarar*"])


@pytest.mark.parametrize("payload", ["CLABE ****1234", INVALID_18_DIGITS, "txn_0001"])
def test_fixture_passes_on_masked_or_invalid(pytester, monkeypatch, capsys, payload):
    body = f'logging.getLogger("app.inner").info("payload=%s", {payload!r})'
    result = _run_inner(pytester, monkeypatch, capsys, body)
    assert result.ret == 0, result.stdout.str()


def test_sensor_fails_on_print(pytester, monkeypatch, capsys, raw_customers):
    body = f'print("clabe", {raw_customers[0]["clabe"]!r})'
    result = _run_inner(pytester, monkeypatch, capsys, body)
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*datos sensibles sin enmascarar en stdout*clabe*"])


def test_sensor_fails_on_stderr(pytester, monkeypatch, capsys, raw_customers):
    body = f'sys.stderr.write("clabe " + {raw_customers[0]["clabe"]!r} + "\\n")'
    result = _run_inner(pytester, monkeypatch, capsys, body)
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*datos sensibles sin enmascarar en stderr*clabe*"])


def test_sensor_attributes_exception_message_leak(pytester, monkeypatch, capsys, raw_customers):
    # The test fails anyway because it raises; the point is that the sensor names the leak.
    body = f'raise ValueError("CLABE " + {raw_customers[0]["clabe"]!r})'
    result = _run_inner(pytester, monkeypatch, capsys, body)
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*datos sensibles sin enmascarar en excepción*clabe*"])


def test_sensor_passes_on_masked_print(pytester, monkeypatch, capsys):
    result = _run_inner(pytester, monkeypatch, capsys, 'print("CLABE ************5678")')
    assert result.ret == 0, result.stdout.str()
