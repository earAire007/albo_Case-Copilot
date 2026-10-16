"""Core banking domain as exposed by the simulated internal system.

Models are frozen: the mock dataset is immutable at runtime. Amounts are integer
cents (MXN); timestamps are ISO 8601 with the America/Mexico_City offset.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TxnType(StrEnum):
    SPEI_IN = "spei_in"
    SPEI_OUT = "spei_out"
    CARD = "card"


class TxnStatus(StrEnum):
    SETTLED = "settled"  # liquidado
    PENDING = "pending"  # pendiente
    RETURNED = "returned"  # devuelto
    REJECTED = "rejected"  # rechazado


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Customer(DomainModel):
    id: str
    name: str
    clabe: str
    card_number: str
    rfc: str
    curp: str
    created_at: datetime


class Transaction(DomainModel):
    id: str
    customer_id: str
    type: TxnType
    status: TxnStatus
    amount: int
    created_at: datetime
    settled_at: datetime | None = None
    # SPEI
    tracking_key: str | None = None
    counterparty_name: str | None = None
    counterparty_clabe: str | None = None
    concept: str | None = None
    return_reason: str | None = None
    cep_available: bool | None = None
    # Card
    merchant: str | None = None
    mcc: str | None = None
    authorization_code: str | None = None
    rejection_reason: str | None = None

    @property
    def is_spei(self) -> bool:
        return self.type in (TxnType.SPEI_IN, TxnType.SPEI_OUT)
