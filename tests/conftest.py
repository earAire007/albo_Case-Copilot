import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest_plugins = ["pytester", "tests.sensitive_logs"]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def raw_customers() -> list[dict]:
    return _load("customers.json")


@pytest.fixture(scope="session")
def raw_transactions() -> list[dict]:
    return _load("transactions.json")


@pytest.fixture(scope="session")
def raw_scenarios() -> dict:
    return _load("scenarios.json")


@pytest.fixture(scope="session")
def repo():
    from backend.mock_core.repository import JsonCoreRepository

    return JsonCoreRepository(DATA_DIR)


@pytest.fixture(scope="session")
def client(repo):
    from backend.mock_core.api import create_app

    return TestClient(create_app(repo))


def fetch_all_transactions(client: TestClient, customer_id: str, **params) -> list[dict]:
    """Walks the paginated listing until next_cursor is exhausted."""
    items: list[dict] = []
    cursor = None
    while True:
        query = {"limit": 50, **params}
        if cursor:
            query["cursor"] = cursor
        resp = client.get(f"/customers/{customer_id}/transactions", params=query)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        items.extend(body["items"])
        cursor = body["next_cursor"]
        if not cursor:
            return items
