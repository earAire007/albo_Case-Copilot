"""Spec 01 — AC5, AC6, AC7: aislamiento por cliente, paginación y solo lectura."""

import pytest
from pydantic import ValidationError

from .conftest import fetch_all_transactions

CUSTOMER_IDS = [f"cus_{i:03d}" for i in range(1, 21)]


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_endpoints_never_return_other_customer_data(client, raw_transactions, customer_id):
    base = f"/customers/{customer_id}"
    assert client.get(base).json()["id"] == customer_id
    assert client.get(f"{base}/summary").json()["customer_id"] == customer_id

    items = fetch_all_transactions(client, customer_id)
    assert items and all(t["customer_id"] == customer_id for t in items)

    for t in items:
        detail = client.get(f"{base}/transactions/{t['id']}").json()
        assert detail["customer_id"] == customer_id
        sub = "card-authorization" if t["type"] == "card" else "spei-status"
        assert (
            client.get(f"{base}/transactions/{t['id']}/{sub}").json()["customer_id"] == customer_id
        )

    foreign = next(t for t in raw_transactions if t["customer_id"] != customer_id)
    for suffix in ("", "/spei-status", "/card-authorization"):
        assert client.get(f"{base}/transactions/{foreign['id']}{suffix}").status_code == 404


def test_unknown_customer_is_404(client):
    assert client.get("/customers/cus_999").status_code == 404
    assert client.get("/customers/cus_999/transactions").status_code == 404
    assert client.get("/customers/cus_999/summary").status_code == 404


def test_type_specific_endpoints_404_on_wrong_type(client, raw_transactions):
    card = next(t for t in raw_transactions if t["type"] == "card")
    spei = next(t for t in raw_transactions if t["type"] != "card")
    assert (
        client.get(
            f"/customers/{card['customer_id']}/transactions/{card['id']}/spei-status"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/customers/{spei['customer_id']}/transactions/{spei['id']}/card-authorization"
        ).status_code
        == 404
    )


def test_limit_above_50_is_422(client):
    assert client.get("/customers/cus_001/transactions", params={"limit": 51}).status_code == 422


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_pagination_covers_all_without_duplicates(client, raw_transactions, customer_id):
    expected = {t["id"] for t in raw_transactions if t["customer_id"] == customer_id}
    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 3}
        if cursor:
            params["cursor"] = cursor
        body = client.get(f"/customers/{customer_id}/transactions", params=params).json()
        assert len(body["items"]) <= 3
        seen.extend(t["id"] for t in body["items"])
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen))
    assert set(seen) == expected


def test_filters_by_type_and_status(client):
    items = fetch_all_transactions(client, "cus_001", type="spei_out", status="settled")
    assert all((t["type"], t["status"]) == ("spei_out", "settled") for t in items)


def test_summary_counts_match_listing(client, raw_transactions):
    body = client.get("/customers/cus_001/summary").json()
    own = [t for t in raw_transactions if t["customer_id"] == "cus_001"]
    assert sum(row["count"] for row in body["by_type_status"]) == len(own)
    assert sum(row["amount"] for row in body["by_type_status"]) == sum(t["amount"] for t in own)


def test_mock_api_has_no_write_routes(client):
    for route in client.app.routes:
        methods = getattr(route, "methods", None) or set()
        assert methods <= {"GET", "HEAD"}, (route.path, methods)
    for method in ("post", "put", "patch", "delete"):
        resp = getattr(client, method)("/customers/cus_001/transactions")
        assert resp.status_code == 405


def test_repository_models_are_immutable(repo):
    customer = repo.get_customer("cus_001")
    with pytest.raises(ValidationError):
        customer.clabe = "000000000000000000"
    page = repo.list_transactions("cus_001", limit=5)
    assert isinstance(page.items, tuple)
    with pytest.raises(ValidationError):
        page.items[0].amount = 1
    assert repo.get_customer("cus_001").clabe != "000000000000000000"
