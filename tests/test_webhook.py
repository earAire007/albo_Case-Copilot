"""Spec 06 — webhook: idempotencia por Idempotency-Key, validación y mensaje enmascarado."""

import json

from backend.domain.sensitive import find_sensitive
from backend.store.store import Store

from .spec06_helpers import client_for, post_ticket


def test_webhook_is_idempotent():
    store = Store(":memory:")
    client = client_for(store)
    first = post_ticket(client)
    again = post_ticket(client)
    assert first.status_code == 202 and again.status_code == 202
    assert first.json()["case_id"] == again.json()["case_id"]
    assert first.json()["status"] == "queued"
    assert len(store.all_rows()["jobs"]) == 1, "un reintento no encola otra vez"

    other_body = post_ticket(client, message="otro texto")
    assert other_body.status_code == 409
    assert post_ticket(client, key=None).status_code == 400
    assert post_ticket(client, key="k-2", customer_id="cus_999").status_code == 422
    assert len(store.all_rows()["cases"]) == 1


def test_webhook_persists_masked_message(raw_customers):
    store = Store(":memory:")
    clabe = raw_customers[3]["clabe"]
    response = post_ticket(client_for(store), message=f"Reembolsen a la CLABE {clabe} ya")
    assert response.status_code == 202
    dumped = json.dumps(store.all_rows(), ensure_ascii=False)
    assert clabe not in dumped and find_sensitive(dumped) == []
    assert "****" + clabe[-4:] in dumped
