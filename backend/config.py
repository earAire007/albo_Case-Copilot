"""Environment configuration: the only place that reads and parses settings.

An empty variable counts as absent and takes the default (`.env.example` ships empty
values on purpose, and compose passes them as ""). An invalid value raises ConfigError
naming the variable and the expected type, never echoing the value: a key pasted into
the wrong variable must not reach the log.
"""

import os
from collections.abc import Callable, Collection


class ConfigError(ValueError):
    """A configuration value that cannot be used; the message names the variable."""


def env_raw(name: str) -> str | None:
    """The stripped value, or None if unset or empty."""
    value = os.environ.get(name, "").strip()
    return value or None


def parse[T](name: str, raw: str, convert: Callable[[str], T], expected: str) -> T:
    try:
        return convert(raw)
    except ValueError:
        raise ConfigError(f"{name}: valor inválido; se espera {expected}") from None


def env_str(name: str, default: str) -> str:
    return env_raw(name) or default


def env_int(name: str, default: int) -> int:
    raw = env_raw(name)
    return default if raw is None else parse(name, raw, int, "un entero")


def env_float(name: str, default: float) -> float:
    raw = env_raw(name)
    return default if raw is None else parse(name, raw, float, "un número")


def env_choice(name: str, default: str, choices: Collection[str]) -> str:
    raw = env_raw(name)
    if raw is None:
        return default
    if raw not in choices:
        raise ConfigError(f"{name}: valor inválido; se espera uno de {', '.join(choices)}")
    return raw
