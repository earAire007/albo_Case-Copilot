"""Mock of the internal core-banking API (spec 01). Read-only: GET routes only.

Returns full, unmasked data on purpose: masking and per-case scoping live at the
MCP boundary (spec 02), never here.
"""

from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from backend.domain.models import Customer, Transaction, TxnStatus, TxnType
from backend.mock_core.repository import (
    CoreRepository,
    InvalidCursorError,
    JsonCoreRepository,
    TransactionPage,
    TransactionSummary,
)

MAX_PAGE_SIZE = 50


class SpeiStatus(BaseModel):
    customer_id: str
    txn_id: str
    type: TxnType
    status: TxnStatus
    amount: int
    created_at: datetime
    settled_at: datetime | None
    tracking_key: str
    counterparty_name: str
    counterparty_clabe: str
    return_reason: str | None
    cep_available: bool


class CardAuthorization(BaseModel):
    customer_id: str
    txn_id: str
    status: TxnStatus
    amount: int
    created_at: datetime
    settled_at: datetime | None
    merchant: str
    mcc: str
    authorization_code: str | None
    rejection_reason: str | None


def create_app(repo: CoreRepository) -> FastAPI:
    app = FastAPI(title="Core bancario simulado", version="0.1.0")

    def require_customer(customer_id: str) -> Customer:
        customer = repo.get_customer(customer_id)
        if customer is None:
            raise HTTPException(404, "customer not found")
        return customer

    def require_transaction(customer_id: str, txn_id: str) -> Transaction:
        require_customer(customer_id)
        txn = repo.get_transaction(customer_id, txn_id)
        if txn is None:
            raise HTTPException(404, "transaction not found")
        return txn

    @app.get("/customers/{customer_id}")
    def get_customer(customer_id: str) -> Customer:
        return require_customer(customer_id)

    @app.get("/customers/{customer_id}/transactions")
    def list_transactions(
        customer_id: str,
        type: TxnType | None = None,
        status: TxnStatus | None = None,
        from_: Annotated[datetime | None, Query(alias="from")] = None,
        to: datetime | None = None,
        limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
        cursor: str | None = None,
    ) -> TransactionPage:
        require_customer(customer_id)
        try:
            return repo.list_transactions(
                customer_id,
                type=type,
                status=status,
                from_=from_,
                to=to,
                limit=limit,
                cursor=cursor,
            )
        except InvalidCursorError:
            raise HTTPException(422, "invalid cursor") from None

    @app.get("/customers/{customer_id}/transactions/{txn_id}")
    def get_transaction(customer_id: str, txn_id: str) -> Transaction:
        return require_transaction(customer_id, txn_id)

    @app.get("/customers/{customer_id}/transactions/{txn_id}/spei-status")
    def get_spei_status(customer_id: str, txn_id: str) -> SpeiStatus:
        txn = require_transaction(customer_id, txn_id)
        if not txn.is_spei:
            raise HTTPException(404, "transaction not found")
        return SpeiStatus(txn_id=txn.id, **txn.model_dump(include=set(SpeiStatus.model_fields)))

    @app.get("/customers/{customer_id}/transactions/{txn_id}/card-authorization")
    def get_card_authorization(customer_id: str, txn_id: str) -> CardAuthorization:
        txn = require_transaction(customer_id, txn_id)
        if txn.type != TxnType.CARD:
            raise HTTPException(404, "transaction not found")
        return CardAuthorization(
            txn_id=txn.id, **txn.model_dump(include=set(CardAuthorization.model_fields))
        )

    @app.get("/customers/{customer_id}/summary")
    def get_summary(
        customer_id: str,
        from_: Annotated[datetime | None, Query(alias="from")] = None,
        to: datetime | None = None,
    ) -> TransactionSummary:
        require_customer(customer_id)
        return repo.summarize(customer_id, from_=from_, to=to)

    return app


app = create_app(JsonCoreRepository())
