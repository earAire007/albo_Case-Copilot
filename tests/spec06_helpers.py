"""Shared helpers for the spec 06 tests: app over an in-memory store, worker runs."""

from datetime import datetime, timedelta
from typing import Any

import anyio
from fastapi.testclient import TestClient

from backend.app.api import create_app
from backend.mock_core.repository import JsonCoreRepository
from backend.store.store import Store
from backend.worker.worker import run_once

from .agent_helpers import output_json
from .test_loop import CONFIG, FakeModel, call, final, step

RECEIVED = datetime.fromisoformat("2026-10-15T12:00:00-06:00")
REPO = JsonCoreRepository()


def client_for(store: Store) -> TestClient:
    return TestClient(create_app(store, REPO, clock=lambda: RECEIVED))


def post_ticket(
    client: TestClient,
    key: str | None = "k-1",
    customer_id: str = "cus_004",
    message: str = "Me cobraron dos veces en Liverpool",
    ticket_id: str = "T-1",
) -> Any:
    headers = {"Idempotency-Key": key} if key is not None else {}
    body = {"ticket_id": ticket_id, "customer_id": customer_id, "message": message}
    return client.post("/webhooks/tickets", json=body, headers=headers)


def work(store: Store, model: FakeModel, now: datetime = RECEIVED) -> str | None:
    async def main() -> str | None:
        return await run_once(store, model, CONFIG, repo=REPO, now=lambda: now)

    return anyio.run(main)


def proposal_model() -> FakeModel:
    """Looks up the card movements, then proposes open_dispute on a real duplicate."""
    action = {"type": "open_dispute", "txn_id": "txn_0166", "justification": "cargo duplicado"}
    return FakeModel(
        step(call("list_transactions", {"type": "card"})),
        final(output_json(citations=[], no_support=True, action=action)),
    )


def case_with_proposal(store: Store, client: TestClient, key: str) -> tuple[str, int]:
    case_id = post_ticket(client, key=key, ticket_id=key).json()["case_id"]
    work(store, proposal_model())
    proposal_id = client.get(f"/cases/{case_id}").json()["proposal"]["id"]
    return case_id, proposal_id


LATER = RECEIVED + timedelta(minutes=30)
