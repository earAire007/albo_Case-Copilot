"""Spec 04 — casos de eval: esquema, referencias a datos reales, distribución, coherencia."""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend.policies.retrieval import build_index
from evals.schema import CASES_DIR, EvalCase, load_cases

REPO_ROOT = Path(__file__).resolve().parent.parent
POISONED_CHUNK = "contracargos#plazos-y-requisitos"
SPEI_PENDING_LIMIT = timedelta(hours=24)  # data/policies/spei-tiempos.md
NON_ADVERSARIAL_SCENARIOS = {
    "spei_out_returned",
    "spei_out_pending_overdue",
    "spei_settled_cep_resend",
    "card_duplicate_charge",
    "card_fraud_burst",
    "card_rejected",
}


@pytest.fixture(scope="module")
def cases() -> list[EvalCase]:
    return load_cases()


def test_eval_cases_schema(cases):
    files = sorted(CASES_DIR.glob("*.json"))
    assert len(files) == 15
    assert len(cases) == 15
    assert len({c.id for c in cases}) == 15


def test_eval_cases_reference_existing_data(cases, raw_customers, raw_transactions, raw_scenarios):
    customers = {c["id"] for c in raw_customers}
    txns = {t["id"]: t for t in raw_transactions}
    scenarios = raw_scenarios["scenarios"]
    chunk_ids = {c.id for c in build_index().chunks}
    for case in cases:
        assert case.customer_id in customers, case.id
        if case.scenario_id is not None:
            assert case.scenario_id in scenarios, case.id
            assert scenarios[case.scenario_id]["customer_id"] == case.customer_id, case.id
        for tool in case.expected.tools:
            if "txn_id" in tool.args:
                txn = txns.get(tool.args["txn_id"])
                assert txn is not None, (case.id, tool.args)
                assert txn["customer_id"] == case.customer_id, (case.id, tool.args)
        for chunk in case.expected.policy_chunks:
            assert chunk in chunk_ids, (case.id, chunk)


def test_eval_cases_distribution(cases):
    normal = [c for c in cases if c.adversarial is None]
    adversarial = [c for c in cases if c.adversarial is not None]
    assert len(normal) == 9 and len(adversarial) == 6
    assert NON_ADVERSARIAL_SCENARIOS <= {c.scenario_id for c in normal}
    assert any(c.expected.action == "none" for c in normal)
    assert any(c.expected.no_support for c in normal)
    vectors = [v for c in adversarial for v in c.adversarial.vectors]  # type: ignore[union-attr]
    assert set(vectors) == {"customer_message", "policy_chunk", "tool_result", "other_account"}
    assert sum(len(c.adversarial.vectors) > 1 for c in adversarial) >= 2  # type: ignore[union-attr]
    assert any(POISONED_CHUNK in c.expected.policy_chunks for c in adversarial)
    assert any(c.expected.action != "none" for c in adversarial)


def test_eval_case_labels_are_consistent(cases, raw_transactions, raw_scenarios):
    txns = {t["id"]: t for t in raw_transactions}
    reference = datetime.fromisoformat(raw_scenarios["reference_date"])
    for case in cases:
        e = case.expected
        assert e.no_support == (e.policy_chunks == []), case.id
        assert e.justification.strip(), case.id
        assert case.as_of == reference, case.id
        if case.adversarial is not None:
            assert e.must_not, case.id
            if "policy_chunk" in case.adversarial.vectors:
                assert POISONED_CHUNK in e.policy_chunks, case.id
        if e.case_type == "spei_pendiente":
            (txn_id,) = {t.args["txn_id"] for t in e.tools if "txn_id" in t.args}
            txn = txns[txn_id]
            assert txn["status"] == "pending", case.id
            age = case.as_of - datetime.fromisoformat(txn["created_at"])
            expected = "open_dispute" if age > SPEI_PENDING_LIMIT else "none"
            assert e.action == expected, (case.id, age)


@pytest.mark.parametrize("importer", ["backend/domain/models.py", "mcp_server/server.py"])
def test_evals_import_contract(tmp_path, importer):
    root = tmp_path / "project"
    for package in ("backend", "mcp_server", "evals"):
        shutil.copytree(
            REPO_ROOT / package, root / package, ignore=shutil.ignore_patterns("__pycache__")
        )
    shutil.copy(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    module = root / importer
    module.write_text(module.read_text() + "\nimport evals.schema  # noqa\n")
    result = subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports")],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode != 0
    assert "the agent never imports eval labels BROKEN" in result.stdout


def test_case_files_are_valid_json():
    for path in sorted(CASES_DIR.glob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))
