"""unmask(): resolve a customer's real sensitive value (spec 02, invariant 4).

Reads it from the repository; it never reverses a masked string. Protected by an
import-linter contract: only the executor (spec 05) may import this module, and it is
never exposed as an MCP tool.
"""

from backend.mock_core.repository import CoreRepository

UNMASKABLE_FIELDS = frozenset({"clabe", "card_number", "rfc", "curp"})


def unmask(repo: CoreRepository, customer_id: str, field: str) -> str:
    if field not in UNMASKABLE_FIELDS:
        raise ValueError(f"field not unmaskable: {field}")
    customer = repo.get_customer(customer_id)
    if customer is None:
        raise LookupError("customer not found")
    value: str = getattr(customer, field)
    return value
