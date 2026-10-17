"""Spec 05a — run_turn: propuesta o requiere humano, rechazos trazados, trazas limpias."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from backend.agent.validators import CaseContext
from backend.domain.sensitive import find_sensitive
from backend.orchestrator.turn import run_turn
from backend.policies.retrieval import search_policies
from backend.store.store import Store
from evals.schema import load_cases

from .agent_helpers import ScriptedModel, context, mcp_tool_results, output_json

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCH = "orchestrator never executes"


def _chunks(query: str) -> list[dict[str, Any]]:
    return [{"id": r["id"], "text": r["text"]["untrusted_text"]} for r in search_policies(query)]


def test_valid_action_creates_pending_proposal():
    store = Store(":memory:")
    tools = mcp_tool_results("cus_004", [("list_transactions", {"type": "card"})])
    model = ScriptedModel(
        output_json(
            citations=[],
            no_support=True,
            action={"type": "open_dispute", "txn_id": "txn_0166", "justification": "duplicado"},
        )
    )
    result = run_turn(store, context(), tools, [], model)
    assert result.status == "proposal_pending" and result.proposal_id is not None
    assert store.decision(result.proposal_id) is None
    assert store.executions(result.proposal_id) == []


def test_rejections_are_traced_with_validator(raw_customers):
    store = Store(":memory:")
    clabe = raw_customers[0]["clabe"]
    tools = mcp_tool_results("cus_004", [("list_transactions", {"type": "card"})])
    leaky = output_json(customer_reply=f"Tu CLABE es {clabe}.", citations=[], no_support=True)
    result = run_turn(store, context(), tools, [], ScriptedModel(leaky))
    assert result.status == "requires_human" and result.proposal_id is None
    rejections = [t for t in store.traces("case_test") if t["step"] == "rejection"]
    assert {t["validator"] for t in rejections} == {"digits"}
    dumped = json.dumps(store.traces("case_test"), ensure_ascii=False)
    assert clabe not in dumped and find_sensitive(dumped) == []
    assert "****" + clabe[-4:] in dumped, "la salida rechazada queda en la traza, enmascarada"
    assert store.rejection_counts() == {"digits": 1}


def test_unparseable_output_requires_human():
    store = Store(":memory:")
    result = run_turn(store, context(), [], [], ScriptedModel("no es json"))
    assert result.status == "requires_human"
    assert store.rejection_counts() == {"schema": 1}


def test_persisted_traces_have_no_sensitive_data(raw_customers, raw_transactions, tmp_path):
    store = Store(str(tmp_path / "traces.db"))
    secrets = {c[f] for c in raw_customers for f in ("clabe", "card_number", "rfc", "curp")}
    secrets |= {t["counterparty_clabe"] for t in raw_transactions if t.get("counterparty_clabe")}
    for case in load_cases():
        calls = [(t.name, dict(t.args)) for t in case.expected.tools]
        tools = mcp_tool_results(case.customer_id, calls)
        chunks = _chunks(case.message)
        ctx = CaseContext(case.id, case.customer_id, case.as_of, case.message)
        # A model that echoes everything it saw: worst case for what reaches the traces.
        echo = output_json(
            customer_reply=case.message,
            citations=[c["id"] for c in chunks],
            no_support=not chunks,
        )
        run_turn(store, ctx, tools, chunks, ScriptedModel(echo))
    rows = store.traces()
    assert len({r["case_id"] for r in rows}) == 15
    every_row = [row for table in store.all_rows().values() for row in table]
    for row in every_row:
        dumped = json.dumps(row, ensure_ascii=False)
        assert find_sensitive(dumped) == [], (row["case_id"], row["step"])
        assert not any(s in dumped for s in secrets), (row["case_id"], row["step"])


def test_store_masks_every_table(raw_customers):
    store = Store(":memory:")
    c = raw_customers[0]
    pid = store.create_proposal(
        "case_x", "open_dispute", "txn_0165", f"CLABE {c['clabe']} RFC {c['rfc']}"
    )
    store.record_decision(pid, approver=f"ops {c['clabe']}", decision="approved")
    dumped = json.dumps(store.all_rows(), ensure_ascii=False)
    assert c["clabe"] not in dumped and c["rfc"] not in dumped and find_sensitive(dumped) == []


def _copy_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    for package in ("backend", "mcp_server", "evals"):
        shutil.copytree(
            REPO_ROOT / package, root / package, ignore=shutil.ignore_patterns("__pycache__")
        )
    shutil.copy(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    return root


@pytest.mark.parametrize(
    ("module", "forbidden", "contract"),
    [
        ("backend/agent/validators.py", "backend.store.store", "agent is pure"),
        ("backend/agent/prompt.py", "backend.executor.executor", "agent is pure"),
        ("backend/agent/output.py", "evals.schema", "agent is pure"),
        (
            "backend/orchestrator/turn.py",
            "backend.executor.executor",
            "orchestrator never executes",
        ),
        ("backend/orchestrator/turn.py", "backend.security.unmask", "orchestrator never executes"),
        ("backend/store/store.py", "backend.security.unmask", "unmask is protected"),
    ],
)
def test_harness_import_contracts(tmp_path, module, forbidden, contract):
    root = _copy_project(tmp_path)
    path = root / module
    path.write_text(path.read_text() + f"\nimport {forbidden}  # noqa\n")
    result = subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports")],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode != 0
    assert any(contract in line and "BROKEN" in line for line in result.stdout.splitlines())


def test_executor_may_import_unmask(tmp_path):
    root = _copy_project(tmp_path)
    path = root / "backend" / "executor" / "executor.py"
    path.write_text(path.read_text() + "\nimport backend.security.unmask  # noqa\n")
    result = subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports")],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode == 0, result.stdout
