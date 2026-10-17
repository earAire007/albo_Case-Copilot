"""Spec 02 — servidor MCP: solo lectura, scoping por sesión, enmascarado, texto no confiable.

Every test goes through a real in-memory MCP client session (mcp.Client), the same
boundary the agent harness will use (spec 05).
"""

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client
from mcp.types import TextContent

from backend.domain.sensitive import find_sensitive
from mcp_server.server import create_server

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = {"get_customer", "list_transactions", "get_spei_status", "get_card_authorization"}
MONEY_WORDS = re.compile(r"refund|reembols|transfer|pay|pago|send|withdraw|retiro", re.IGNORECASE)
CUSTOMER_IDS = [f"cus_{i:03d}" for i in range(1, 21)]


def with_client[T](repo, customer_id: str, fn: Callable[[Client], Awaitable[T]]) -> T:
    server = create_server(repo, customer_id)

    async def main() -> T:
        async with Client(server) as client:
            return await fn(client)

    return anyio.run(main)


async def call(client: Client, name: str, args: dict[str, Any] | None = None) -> tuple[bool, Any]:
    result = await client.call_tool(name, args or {})
    block = result.content[0]
    assert isinstance(block, TextContent)
    return result.is_error, (block.text if result.is_error else json.loads(block.text))


async def all_transactions(client: Client, **filters: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        args = {"limit": 20, **filters, **({"cursor": cursor} if cursor else {})}
        is_error, page = await call(client, "list_transactions", args)
        assert not is_error, page
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            return items


def test_mcp_exposes_no_money_moving_tool(repo):
    async def fn(client: Client):
        return (await client.list_tools()).tools

    tools = with_client(repo, "cus_001", fn)
    assert {t.name for t in tools} == TOOLS
    for tool in tools:
        assert tool.annotations is not None and tool.annotations.read_only_hint is True, tool.name
        assert not MONEY_WORDS.search(tool.name), tool.name


def test_unmask_not_exposed_as_tool(repo):
    async def fn(client: Client):
        return (await client.list_tools()).tools

    names = {t.name for t in with_client(repo, "cus_001", fn)}
    assert not any("unmask" in n for n in names)


def test_create_server_rejects_unknown_customer(repo):
    with pytest.raises(ValueError):
        create_server(repo, "cus_999")


def test_mcp_tools_ignore_model_supplied_customer_id(repo):
    async def fn(client: Client):
        schemas = [t.input_schema for t in (await client.list_tools()).tools]
        _, customer = await call(client, "get_customer", {"customer_id": "cus_002"})
        _, page = await call(client, "list_transactions", {"customer_id": "cus_002", "limit": 20})
        return schemas, customer, page

    schemas, customer, page = with_client(repo, "cus_001", fn)
    for schema in schemas:
        assert "customer_id" not in schema.get("properties", {})
    assert customer["id"] == "cus_001"
    assert page["items"] and all(t["customer_id"] == "cus_001" for t in page["items"])


def test_other_account_scenario_is_unreachable(repo, raw_scenarios, raw_transactions):
    scenario = raw_scenarios["scenarios"]["adv_other_account"]
    target_txns = [
        t for t in raw_transactions if t["customer_id"] == scenario["target_customer_id"]
    ]

    async def fn(client: Client):
        missing = {
            tool: (await call(client, tool, {"txn_id": "txn_9999"}))[1]
            for tool in ("get_spei_status", "get_card_authorization")
        }
        results = []
        for t in target_txns:
            tool = "get_card_authorization" if t["type"] == "card" else "get_spei_status"
            results.append((tool, *await call(client, tool, {"txn_id": t["id"]})))
        own = await all_transactions(client)
        return missing, results, own

    missing, results, own = with_client(repo, scenario["customer_id"], fn)
    assert target_txns
    for tool, is_error, message in results:
        # Same tool, same error as a nonexistent id: no oracle for other customers' ids.
        assert is_error and message == missing[tool], "debe ser indistinguible de un id inexistente"
    assert {t["id"] for t in target_txns}.isdisjoint({t["id"] for t in own})


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_mask_applied_before_model_and_traces(repo, customer_id):
    async def fn(client: Client):
        outputs: list[Any] = [(await call(client, "get_customer"))[1]]
        txns = await all_transactions(client)
        outputs.append(txns)
        for t in txns:
            tool = "get_card_authorization" if t["type"] == "card" else "get_spei_status"
            is_error, payload = await call(client, tool, {"txn_id": t["id"]})
            assert not is_error, payload
            outputs.append(payload)
        return outputs

    for output in with_client(repo, customer_id, fn):
        serialized = json.dumps(output, ensure_ascii=False)
        assert find_sensitive(serialized) == [], customer_id


def test_mask_reuses_detector_and_keeps_tracking_key(repo, raw_transactions):
    spei = next(t for t in raw_transactions if t["type"] != "card")

    async def fn(client: Client):
        return await call(client, "get_spei_status", {"txn_id": spei["id"]})

    is_error, status = with_client(repo, spei["customer_id"], fn)
    assert not is_error
    assert status["tracking_key"] == spei["tracking_key"]
    assert status["counterparty_clabe"] == "****" + spei["counterparty_clabe"][-4:]


def test_untrusted_fields_are_marked(repo, raw_scenarios, raw_transactions):
    scenario = raw_scenarios["scenarios"]["adv_tool_result_injection"]
    (txn_id,) = scenario["txn_ids"]
    raw = next(t for t in raw_transactions if t["id"] == txn_id)

    async def fn(client: Client):
        items = await all_transactions(client)
        _, status = await call(client, "get_spei_status", {"txn_id": txn_id})
        return items, status

    items, status = with_client(repo, scenario["customer_id"], fn)
    for t in items:
        fields = (
            {"merchant": "comercio"}
            if t["type"] == "card"
            else {
                "concept": "spei_ordenante",
                "counterparty_name": "spei_ordenante",
            }
        )
        for field, source in fields.items():
            assert set(t[field]) == {"untrusted_text", "source"}, (t["id"], field)
            assert t[field]["source"] == source
    injected = next(t for t in items if t["id"] == txn_id)
    assert injected["concept"]["untrusted_text"] == raw["concept"]
    assert status["counterparty_name"] == {
        "untrusted_text": raw["counterparty_name"],
        "source": "spei_ordenante",
    }


def test_list_transactions_is_capped(repo, raw_transactions):
    expected = {t["id"] for t in raw_transactions if t["customer_id"] == "cus_001"}

    async def fn(client: Client):
        too_big = await call(client, "list_transactions", {"limit": 21})
        return too_big, await all_transactions(client)

    (is_error, _), items = with_client(repo, "cus_001", fn)
    assert is_error
    ids = [t["id"] for t in items]
    assert len(ids) == len(set(ids)) and set(ids) == expected


def test_list_transactions_reports_total_and_has_more(repo, raw_transactions):
    # No customer has more than 20 movements in the dataset; a smaller page exercises
    # the same total/has_more logic.
    total = sum(1 for t in raw_transactions if t["customer_id"] == "cus_001")
    assert total > 3

    async def fn(client: Client):
        pages = []
        cursor = None
        while True:
            args = {"limit": 3, **({"cursor": cursor} if cursor else {})}
            _, page = await call(client, "list_transactions", args)
            pages.append(page)
            cursor = page["next_cursor"]
            if not cursor:
                return pages

    pages = with_client(repo, "cus_001", fn)
    first, last = pages[0], pages[-1]
    assert first["total"] == total and first["has_more"] is True and first["next_cursor"]
    assert last["total"] == total and last["has_more"] is False and last["next_cursor"] is None
    assert all(p["has_more"] for p in pages[:-1])


def test_unmask_import_from_mcp_server_breaks_contracts(tmp_path):
    root = tmp_path / "project"
    for package in ("backend", "mcp_server"):
        shutil.copytree(
            REPO_ROOT / package, root / package, ignore=shutil.ignore_patterns("__pycache__")
        )
    shutil.copy(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    server = root / "mcp_server" / "server.py"
    server.write_text(server.read_text() + "\nfrom backend.security import unmask  # noqa\n")
    result = subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports")],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode != 0
    assert "BROKEN" in result.stdout
