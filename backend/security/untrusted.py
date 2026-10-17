"""Single shape for untrusted content (invariant 5): third-party text and policy chunks.

The harness (spec 05) delimits anything in this envelope as data, never instructions.
Shared by the MCP server (spec 02) and the policy retriever (spec 03).
"""

from typing import TypedDict


class UntrustedText(TypedDict):
    untrusted_text: str
    source: str


def wrap_untrusted(text: str, source: str) -> UntrustedText:
    return {"untrusted_text": text, "source": source}
