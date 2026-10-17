"""In-process queue worker (spec 06): takes one job, runs the case with the real loop
(spec 05b) against an MCP session bound to the case's customer, stores the final status.

Never approves or executes (import-linter). A job whose case already has a final status
or a proposal is closed without calling the model: a queue retry costs nothing and never
duplicates a proposal (UNIQUE(case_id) backs this up).
"""

from collections.abc import Callable
from datetime import datetime, timedelta

from mcp import Client

from backend.agent.model import ToolCallingModel
from backend.agent.validators import CaseContext
from backend.mock_core.repository import CoreRepository
from backend.orchestrator.loop import LoopConfig, run_case
from backend.orchestrator.mcp_session import McpToolSession
from backend.store.store import FINAL_STATUSES, Store
from mcp_server.server import create_server

STUCK_AFTER = timedelta(minutes=10)
MAX_ATTEMPTS = 2


async def run_once(
    store: Store,
    model: ToolCallingModel,
    config: LoopConfig,
    *,
    repo: CoreRepository,
    now: Callable[[], datetime],
    stuck_after: timedelta = STUCK_AFTER,
    max_attempts: int = MAX_ATTEMPTS,
) -> str | None:
    """Process at most one job; returns the processed case id, or None if idle."""
    current = now()
    store.requeue_stuck_jobs(older_than=current - stuck_after, max_attempts=max_attempts)
    job = store.claim_job(now=current)
    if job is None:
        return None
    case = store.get_case(job["case_id"])
    if case["status"] in FINAL_STATUSES:
        store.finish_job(job["id"], "done")
        return None
    if store.proposal_for_case(case["id"]) is not None:
        # The worker died after the proposal but before saving the status: close it.
        store.set_case_status(case["id"], "proposal_pending")
        store.finish_job(job["id"], "done")
        return None
    ctx = CaseContext(
        case_id=case["id"],
        customer_id=case["customer_id"],
        as_of=datetime.fromisoformat(case["as_of"]),
        message=case["message"],
    )
    try:
        async with Client(create_server(repo, case["customer_id"])) as client:
            result = await run_case(store, ctx, McpToolSession(client), model, config)
    except Exception as exc:
        store.add_trace(case["id"], "worker_error", {"kind": type(exc).__name__})
        if job["attempts"] >= max_attempts:
            store.finish_job(job["id"], "failed")
            store.set_case_status(case["id"], "requires_human")
        else:
            store.finish_job(job["id"], "queued")
        return case["id"]
    store.set_case_status(case["id"], result.status)
    store.finish_job(job["id"], "done")
    return case["id"]
