"""Model client port. Spec 05a uses test doubles; spec 05b plugs in the real provider."""

from typing import Protocol


class ModelClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...
