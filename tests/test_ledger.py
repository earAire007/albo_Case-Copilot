"""Spec 06 — registro protegido de decisiones y ejecuciones (invariante 2)."""

import re
import shutil
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from backend.store import ledger
from backend.store.ledger import NotApprovedError
from backend.store.store import Store

REPO_ROOT = Path(__file__).resolve().parent.parent


def _proposal(store: Store) -> int:
    return store.create_proposal("case_l", "open_dispute", "txn_0165", "x", customer_id="cus_004")


def test_execution_requires_approval_in_same_transaction():
    store = Store(":memory:")
    pid = _proposal(store)
    # Called straight on the ledger, bypassing the executor: still refused, nothing inserted.
    with pytest.raises(NotApprovedError):
        ledger.record_execution(store, pid, {"action": "open_dispute"})
    assert ledger.executions(store, pid) == []
    ledger.record_decision(store, pid, approver="ops", decision="rejected")
    with pytest.raises(NotApprovedError):
        ledger.record_execution(store, pid, {"action": "open_dispute"})
    assert ledger.executions(store, pid) == []


def test_execution_after_approval_is_recorded_once():
    store = Store(":memory:")
    pid = _proposal(store)
    ledger.record_decision(store, pid, approver="ops", decision="approved")
    first = ledger.record_execution(store, pid, {"n": 1})
    second = ledger.record_execution(store, pid, {"n": 2})
    assert first == second == {"n": 1}
    assert len(ledger.executions(store, pid)) == 1


def _copy_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    for package in ("backend", "mcp_server", "evals"):
        shutil.copytree(
            REPO_ROOT / package, root / package, ignore=shutil.ignore_patterns("__pycache__")
        )
    shutil.copy(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    return root


def _broken(root: Path) -> list[str]:
    out = subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports")],
        capture_output=True,
        text=True,
        cwd=root,
    ).stdout
    return [line for line in out.splitlines() if "BROKEN" in line]


@pytest.mark.parametrize(
    "module", ["backend/orchestrator/turn.py", "backend/store/store.py", "backend/worker/worker.py"]
)
def test_ledger_is_protected(tmp_path, module):
    root = _copy_project(tmp_path)
    path = root / module
    path.write_text(path.read_text() + "\nimport backend.store.ledger  # noqa\n")
    assert any("ledger is protected" in line for line in _broken(root))


def test_approval_never_touches_the_model(tmp_path):
    root = _copy_project(tmp_path)
    path = root / "backend" / "approval" / "service.py"
    path.write_text(path.read_text() + "\nimport backend.llm.anthropic_client  # noqa\n")
    assert any("approval never touches the model" in line for line in _broken(root))


def test_worker_never_approves_or_executes(tmp_path):
    root = _copy_project(tmp_path)
    path = root / "backend" / "worker" / "worker.py"
    path.write_text(path.read_text() + "\nimport backend.approval.service  # noqa\n")
    assert any("worker and orchestrator never approve" in line for line in _broken(root))


def test_decision_and_execution_inserts_only_in_ledger():
    """Textual guard: raw SQL into decisions/executions outside the ledger (residual risk)."""
    pattern = re.compile(r"INSERT\s+(OR\s+\w+\s+)?INTO\s+(decisions|executions)\b", re.IGNORECASE)
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for top in ("backend", "mcp_server", "scripts", "data", "evals")
        for path in sorted((REPO_ROOT / top).rglob("*.py"))
        if path != REPO_ROOT / "backend" / "store" / "ledger.py"
        and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE decisions SET decision = 'approved'",
        "DELETE FROM decisions",
        "INSERT OR REPLACE INTO decisions (proposal_id, approver, decision, decided_at)"
        " VALUES (1, 'x', 'approved', 'now')",
        "UPDATE executions SET result = '{}'",
        "DELETE FROM executions",
    ],
)
def test_ledger_tables_are_insert_only(sql):
    store = Store(":memory:")
    pid = _proposal(store)
    ledger.record_decision(store, pid, approver="ops", decision="rejected")
    # A second, executed proposal so both ledger tables have rows to tamper with.
    executed = store.create_proposal(
        "case_m", "open_dispute", "txn_0166", "x", customer_id="cus_004"
    )
    ledger.record_decision(store, executed, approver="ops", decision="approved")
    ledger.record_execution(store, executed, {"n": 1})
    with pytest.raises(sqlite3.DatabaseError):
        with store.connection:
            store.connection.execute(sql)
    recorded = ledger.decision(store, pid)
    assert recorded is not None and recorded["decision"] == "rejected"
    assert [e["result"] for e in ledger.executions(store, executed)] == [{"n": 1}]


def test_ledger_rejects_empty_approver():
    store = Store(":memory:")
    pid = _proposal(store)
    with pytest.raises(ValueError):
        ledger.record_decision(store, pid, approver="  ", decision="approved")
    assert ledger.decision(store, pid) is None


def _race_once() -> None:
    from backend.approval.service import ConflictError, approve, reject

    store = Store(":memory:")
    pid = _proposal(store)
    outcomes: dict[str, str] = {}
    errors: list[BaseException] = []
    barrier = threading.Barrier(3)

    def run(name: str, fn: Callable[[], object]) -> None:
        barrier.wait()
        try:
            fn()
            outcomes[name] = "ok"
        except ConflictError:
            outcomes[name] = "conflict"
        except BaseException as exc:  # anything else is a bug
            errors.append(exc)

    def noise() -> None:
        barrier.wait()
        for i in range(20):
            store.add_trace("case_l", "noise", {"i": i})

    threads = [
        threading.Thread(target=run, args=("approve", lambda: approve(store, pid, "ops"))),
        threading.Thread(target=run, args=("reject", lambda: reject(store, pid, "ops", "x"))),
        threading.Thread(target=noise),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    recorded = ledger.decision(store, pid)
    assert recorded is not None
    winner = "approve" if recorded["decision"] == "approved" else "reject"
    loser = "reject" if winner == "approve" else "approve"
    assert outcomes[winner] == "ok" and outcomes[loser] == "conflict"
    assert len(ledger.executions(store, pid)) == (1 if winner == "approve" else 0)


def test_concurrent_approve_and_reject_stay_consistent():
    """FastAPI's thread pool and the worker share one Store: no unexpected errors, and
    what each call answered matches what the ledger recorded."""
    for _ in range(60):
        _race_once()


def test_decision_and_execution_writes_only_in_ledger():
    """Textual guard, widened: no INSERT/UPDATE/DELETE/REPLACE on the ledger tables."""
    pattern = re.compile(
        r"(INSERT\s+(OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+(decisions|executions)\b"
        r"|DROP\s+TRIGGER",
        re.IGNORECASE,
    )
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for top in ("backend", "mcp_server", "scripts", "data", "evals")
        for path in sorted((REPO_ROOT / top).rglob("*.py"))
        if path != REPO_ROOT / "backend" / "store" / "ledger.py"
        and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
