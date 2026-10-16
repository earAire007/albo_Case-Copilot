"""Spec 01 — AC1, AC2, AC3: generador determinista e integridad del dataset."""

import subprocess
import sys
from collections import Counter
from itertools import product

from backend.domain.validators import CURP_RE, RFC_RE, clabe_is_valid, luhn_is_valid

from .conftest import DATA_DIR

DATASET_FILES = ("customers.json", "transactions.json", "scenarios.json")
TYPES = ("spei_in", "spei_out", "card")
STATUSES = ("settled", "pending", "returned", "rejected")


def test_generator_is_byte_deterministic(tmp_path):
    subprocess.run(
        [sys.executable, str(DATA_DIR / "generate.py"), "--out", str(tmp_path)],
        check=True,
    )
    for name in DATASET_FILES:
        assert (tmp_path / name).read_bytes() == (DATA_DIR / name).read_bytes(), name


def test_counts_and_type_status_coverage(raw_customers, raw_transactions):
    assert len(raw_customers) == 20
    assert 180 <= len(raw_transactions) <= 220
    combos = Counter((t["type"], t["status"]) for t in raw_transactions)
    missing = [c for c in product(TYPES, STATUSES) if combos[c] == 0]
    assert not missing, f"combinaciones sin movimientos: {missing}"


def test_transactions_reference_existing_customers(raw_customers, raw_transactions):
    customer_ids = {c["id"] for c in raw_customers}
    assert {t["customer_id"] for t in raw_transactions} <= customer_ids
    assert len({t["id"] for t in raw_transactions}) == len(raw_transactions)


def test_identifiers_are_valid_and_unique(raw_customers):
    for c in raw_customers:
        assert clabe_is_valid(c["clabe"]), c["id"]
        assert luhn_is_valid(c["card_number"]), c["id"]
        assert c["card_number"].startswith("9"), "BIN no emitido"
        assert RFC_RE.fullmatch(c["rfc"]), c["id"]
        assert CURP_RE.fullmatch(c["curp"]), c["id"]
    for field in ("clabe", "card_number", "rfc", "curp"):
        values = [c[field] for c in raw_customers]
        assert len(set(values)) == len(values), f"{field} duplicado"


def test_spei_counterparty_clabes_are_valid(raw_transactions):
    for t in raw_transactions:
        if t["type"] != "card":
            assert clabe_is_valid(t["counterparty_clabe"]), t["id"]
