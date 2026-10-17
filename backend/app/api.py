"""Copilot API (spec 06): ticket webhook, case views and the approval endpoints the
operations console (spec 07) uses.

- Webhook: idempotent by the mandatory `Idempotency-Key` header (same key + same body ->
  same case; other body -> 409). The message is stored masked (data minimization).
- Approval: approve = decision + execution in one call (the executor is idempotent);
  terminal states; empty approver -> 422. The approver is not authenticated (residual
  risk, see DESIGN.md).
- Reply edit (spec 07): `PUT /cases/{id}/reply`, rules in backend.approval (422/404/409).
- Case views expose masked data only, never thinking blocks.
"""

import hashlib
import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any

import anyio
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from backend.approval.service import (
    ConflictError,
    approve,
    decision_of,
    edit_reply,
    execution_of,
    model_reply,
    reject,
)
from backend.mock_core.repository import CoreRepository, JsonCoreRepository
from backend.store.store import IdempotencyConflictError, Store

MEXICO_CITY = timezone(timedelta(hours=-6))
CONSOLE_DIST = Path(__file__).resolve().parents[2] / "console" / "dist"
_HIDDEN_TRACE_STEPS = frozenset({"prompt"})  # full prompts stay in the DB, not in the console


class TicketIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approver: str


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    editor: str
    final_reply: str


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approver: str
    reason: str = ""


def _body_hash(ticket: TicketIn) -> str:
    canonical = json.dumps(ticket.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _last_payload(store: Store, case_id: str, step: str) -> dict[str, Any] | None:
    rows = [t for t in store.traces(case_id) if t["step"] == step]
    return rows[-1]["payload"] if rows else None


def _case_view(store: Store, case: dict[str, Any]) -> dict[str, Any]:
    answer = _last_payload(store, case["id"], "answer") or {}
    summary = _last_payload(store, case["id"], "reasoning_summary") or {}
    proposal = store.proposal_for_case(case["id"])
    return {
        "id": case["id"],
        "ticket_id": case["ticket_id"],
        "customer_id": case["customer_id"],
        "status": case["status"],
        "as_of": case["as_of"],
        "message": case["message"],
        "case_type": answer.get("case_type"),
        "reply": model_reply(store, case["id"]),
        "final_reply": case["final_reply"],
        "edited_by": case["edited_by"],
        "edited_at": case["edited_at"],
        "reasoning_summary": summary.get("text"),
        "proposal": None
        if proposal is None
        else {
            "id": proposal["id"],
            "action": proposal["action"],
            "txn_id": proposal["txn_id"],
            "justification": proposal["justification"],
            "decision": decision_of(store, proposal["id"]),
            "execution": execution_of(store, proposal["id"]),
        },
    }


def create_app(
    store: Store,
    repo: CoreRepository,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(MEXICO_CITY),
    worker: Callable[[], Any] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if worker is None:
            yield
            return
        async with anyio.create_task_group() as tg:
            tg.start_soon(worker)
            yield
            tg.cancel_scope.cancel()

    app = FastAPI(title="Copiloto de casos", version="0.1.0", lifespan=lifespan)

    @app.post("/webhooks/tickets", status_code=202)
    def receive_ticket(
        ticket: TicketIn,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, str]:
        if not idempotency_key or not idempotency_key.strip():
            raise HTTPException(400, "Idempotency-Key es obligatoria")
        if repo.get_customer(ticket.customer_id) is None:
            raise HTTPException(422, "customer_id inexistente")
        try:
            case, _ = store.create_case(
                idempotency_key=idempotency_key.strip(),
                body_hash=_body_hash(ticket),
                ticket_id=ticket.ticket_id,
                customer_id=ticket.customer_id,
                message=ticket.message,
                as_of=clock(),
            )
        except IdempotencyConflictError:
            raise HTTPException(409, "la clave ya se usó con otro cuerpo") from None
        return {"case_id": case["id"], "status": case["status"]}

    @app.get("/cases")
    def list_cases(status: str | None = None) -> list[dict[str, Any]]:
        return [_case_view(store, c) for c in store.list_cases(status)]

    @app.get("/cases/{case_id}")
    def get_case(case_id: str) -> dict[str, Any]:
        try:
            return _case_view(store, store.get_case(case_id))
        except KeyError:
            raise HTTPException(404, "caso inexistente") from None

    @app.get("/cases/{case_id}/trace")
    def get_trace(case_id: str) -> list[dict[str, Any]]:
        try:
            store.get_case(case_id)
        except KeyError:
            raise HTTPException(404, "caso inexistente") from None
        return [
            {"step": t["step"], "validator": t["validator"], "payload": t["payload"],
             "created_at": t["created_at"]}
            for t in store.traces(case_id)
            if t["step"] not in _HIDDEN_TRACE_STEPS
        ]  # fmt: skip

    @app.put("/cases/{case_id}/reply")
    def put_reply(case_id: str, body: ReplyIn) -> dict[str, Any]:
        try:
            return _case_view(store, edit_reply(store, case_id, body.editor, body.final_reply))
        except KeyError:
            raise HTTPException(404, "caso inexistente") from None
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/proposals/{proposal_id}/approve")
    def approve_proposal(proposal_id: int, body: ApproveIn) -> dict[str, Any]:
        try:
            return approve(store, proposal_id, body.approver)
        except KeyError:
            raise HTTPException(404, "propuesta inexistente") from None
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/proposals/{proposal_id}/reject")
    def reject_proposal(proposal_id: int, body: RejectIn) -> dict[str, Any]:
        try:
            return reject(store, proposal_id, body.approver, body.reason)
        except KeyError:
            raise HTTPException(404, "propuesta inexistente") from None
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    return app


def _production_app() -> FastAPI:
    from backend.llm.anthropic_client import AnthropicModel, LlmSettings
    from backend.orchestrator.loop import LoopConfig
    from backend.worker.worker import run_once

    store = Store()
    repo = JsonCoreRepository()
    model = AnthropicModel(LlmSettings.from_env())
    config = LoopConfig(
        price_input_per_mtok=float(os.environ.get("PRICE_INPUT_PER_MTOK", "4.0")),
        price_output_per_mtok=float(os.environ.get("PRICE_OUTPUT_PER_MTOK", "20.0")),
    )

    async def worker_loop() -> None:
        while True:
            processed = await run_once(
                store, model, config, repo=repo, now=lambda: datetime.now(MEXICO_CITY)
            )
            if processed is None:
                await anyio.sleep(1.0)

    # Spec 08: the API under /api and the console build at / (one service). A mounted
    # sub-app does not run its lifespan, so the worker belongs to the outer app.
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with anyio.create_task_group() as tg:
            tg.start_soon(worker_loop)
            yield
            tg.cancel_scope.cancel()

    app = FastAPI(title="Copiloto de casos", lifespan=lifespan)
    app.mount("/api", create_app(store, repo))
    console = Path(os.environ.get("CONSOLE_DIST", str(CONSOLE_DIST)))
    if console.is_dir():
        app.mount("/", StaticFiles(directory=console, html=True), name="console")
    return app
