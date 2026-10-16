"""Pytest plugin: fail any test whose logs contain unmasked CLABE, card, RFC or CURP.

Autouse and without opt-out on purpose: a leak in a log is a bug in the code,
never a test to skip (AGENTS.md, reglas no negociables).
"""

import logging
from collections.abc import Iterator

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
