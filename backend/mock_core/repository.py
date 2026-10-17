"""Read-only access to the simulated core-banking system.

`CoreRepository` is the only way the API (and later the MCP server) reaches the data,
so the JSON-backed implementation can be swapped without touching callers. The
dataset is loaded once and never mutated: application state lives in SQLite (specs 05/06).
"""

import base64
import binascii
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.models import Customer, Transaction, TxnStatus, TxnType

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class InvalidCursorError(ValueError):
    pass


class TransactionPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[Transaction, ...]
    total: int  # movements matching the filters, across all pages
    next_cursor: str | None


class SummaryRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: TxnType
    status: TxnStatus
    count: int
    amount: int


class TransactionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    customer_id: str
    from_: datetime | None = Field(serialization_alias="from")
    to: datetime | None
    total_count: int
    by_type_status: tuple[SummaryRow, ...]


class CoreRepository(Protocol):
    def get_customer(self, customer_id: str) -> Customer | None: ...

    def list_transactions(
        self,
        customer_id: str,
        *,
        type: TxnType | None = None,
        status: TxnStatus | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> TransactionPage: ...

    def get_transaction(self, customer_id: str, txn_id: str) -> Transaction | None: ...

    def summarize(
        self, customer_id: str, *, from_: datetime | None = None, to: datetime | None = None
    ) -> TransactionSummary: ...


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode()


def _decode_cursor(cursor: str) -> int:
    try:
        prefix, value = base64.urlsafe_b64decode(cursor.encode()).decode().split(":", 1)
        offset = int(value)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidCursorError(cursor) from exc
    if prefix != "o" or offset < 0:
        raise InvalidCursorError(cursor)
    return offset


def _in_range(txn: Transaction, from_: datetime | None, to: datetime | None) -> bool:
    return (from_ is None or txn.created_at >= from_) and (to is None or txn.created_at <= to)


class JsonCoreRepository:
    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR):
        customers = json.loads((data_dir / "customers.json").read_text(encoding="utf-8"))
        transactions = json.loads((data_dir / "transactions.json").read_text(encoding="utf-8"))

        self._customers: dict[str, Customer] = {
            c.id: c for c in (Customer.model_validate(raw) for raw in customers)
        }
        grouped: dict[str, list[Transaction]] = defaultdict(list)
        for raw in transactions:
            txn = Transaction.model_validate(raw)
            grouped[txn.customer_id].append(txn)
        # Newest first, id as tie-breaker: stable order for offset pagination.
        self._transactions: dict[str, tuple[Transaction, ...]] = {
            cid: tuple(sorted(txns, key=lambda t: (t.created_at, t.id), reverse=True))
            for cid, txns in grouped.items()
        }

    def get_customer(self, customer_id: str) -> Customer | None:
        return self._customers.get(customer_id)

    def list_transactions(
        self,
        customer_id: str,
        *,
        type: TxnType | None = None,
        status: TxnStatus | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> TransactionPage:
        matching = [
            t
            for t in self._transactions.get(customer_id, ())
            if (type is None or t.type == type)
            and (status is None or t.status == status)
            and _in_range(t, from_, to)
        ]
        offset = _decode_cursor(cursor) if cursor else 0
        end = offset + limit
        return TransactionPage(
            items=tuple(matching[offset:end]),
            total=len(matching),
            next_cursor=_encode_cursor(end) if end < len(matching) else None,
        )

    def get_transaction(self, customer_id: str, txn_id: str) -> Transaction | None:
        return next((t for t in self._transactions.get(customer_id, ()) if t.id == txn_id), None)

    def summarize(
        self, customer_id: str, *, from_: datetime | None = None, to: datetime | None = None
    ) -> TransactionSummary:
        counts: dict[tuple[TxnType, TxnStatus], list[int]] = defaultdict(lambda: [0, 0])
        for t in self._transactions.get(customer_id, ()):
            if _in_range(t, from_, to):
                counts[(t.type, t.status)][0] += 1
                counts[(t.type, t.status)][1] += t.amount
        rows = tuple(
            SummaryRow(type=k[0], status=k[1], count=v[0], amount=v[1])
            for k, v in sorted(counts.items())
        )
        return TransactionSummary(
            customer_id=customer_id,
            from_=from_,
            to=to,
            total_count=sum(r.count for r in rows),
            by_type_status=rows,
        )
