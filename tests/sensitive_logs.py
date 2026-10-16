"""Pytest plugin: fail any test that leaks an unmasked CLABE, card, RFC or CURP.

Two sensors, both without opt-out on purpose: a leak is a bug in the code, never a
test to skip (AGENTS.md, reglas no negociables).

- Logs: autouse fixture with a root-logger handler at DEBUG.
- stdout, stderr and exception text: `pytest_runtest_makereport` wrapper that scans
  the captured sections and longrepr of each phase. No capture fixture is requested,
  so it never clashes with tests that use capsys/capfd.

Blind spots: output a test consumes itself (capsys.readouterr), runs with `-s`, and
exceptions caught without being printed or logged.
"""

import logging
from collections.abc import Generator, Iterator

import pytest

from backend.domain.sensitive import find_sensitive


class _CollectingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.texts: list[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            text += "\n" + record.exc_text
        self.texts.append((record.name, text))


@pytest.fixture(autouse=True)
def _no_sensitive_data_in_logs() -> Iterator[None]:
    root = logging.getLogger()
    handler = _CollectingHandler()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)

    leaks = [
        f"{logger}: {', '.join(f.kind for f in found)}"
        for logger, text in handler.texts
        if (found := find_sensitive(text))
    ]
    if leaks:
        pytest.fail("datos sensibles sin enmascarar en logs:\n" + "\n".join(leaks), pytrace=False)


_STREAMS = {"Captured stdout": "stdout", "Captured stderr": "stderr"}


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    leaks: list[str] = []
    for title, content in report.sections:
        source = next((s for prefix, s in _STREAMS.items() if title.startswith(prefix)), None)
        if source and (found := find_sensitive(content)):
            leaks.append(f"{source} ({report.when}): {', '.join(f.kind for f in found)}")
    if report.longrepr and (found := find_sensitive(str(report.longrepr))):
        leaks.append(f"excepción ({report.when}): {', '.join(f.kind for f in found)}")
    if leaks:
        message = "\n".join(f"datos sensibles sin enmascarar en {leak}" for leak in leaks)
        original = f"\n\n{report.longrepr}" if report.longrepr else ""
        report.outcome = "failed"
        report.longrepr = message + original
    return report
