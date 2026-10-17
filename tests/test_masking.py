"""Spec 02 — enmascarado (AC4, unitario) y unmask mínimo."""

import pytest

from backend.domain.sensitive import find_sensitive
from backend.security.masking import mask
from backend.security.unmask import unmask


def test_mask_fields_by_kind(raw_customers, raw_transactions):
    c = raw_customers[0]
    spei = next(t for t in raw_transactions if t["type"] != "card")
    masked = mask(
        {
            **c,
            "counterparty_clabe": spei["counterparty_clabe"],
            "tracking_key": spei["tracking_key"],
        }
    )
    assert masked["clabe"] == "****" + c["clabe"][-4:]
    assert masked["card_number"] == "****" + c["card_number"][-4:]
    assert masked["rfc"] == "[RFC]"
    assert masked["curp"] == "[CURP]"
    assert masked["counterparty_clabe"] == "****" + spei["counterparty_clabe"][-4:]
    assert masked["tracking_key"] == spei["tracking_key"]
    assert masked["id"] == c["id"] and masked["name"] == c["name"]


def test_mask_free_text_uses_detector(raw_customers):
    c = raw_customers[0]
    card_spaced = " ".join(c["card_number"][i : i + 4] for i in range(0, 16, 4))
    text = (
        f"clabe {c['clabe']} tarjeta {card_spaced} rfc {c['rfc']} curp {c['curp']} "
        f"ref {'7' * 24} fin"
    )
    out = mask({"note": text, "nested": [{"deep": text}]})
    nested = out["nested"]
    assert isinstance(nested, list) and isinstance(nested[0], dict)
    for value in (out["note"], nested[0]["deep"]):
        assert isinstance(value, str)
        assert find_sensitive(value) == []
        assert "****" + c["clabe"][-4:] in value
        assert "****" + c["card_number"][-4:] in value
        assert "[RFC]" in value and "[CURP]" in value and "[LONG_NUMBER]" in value
        assert c["rfc"] not in value and c["curp"] not in value and "7" * 24 not in value
        assert value.startswith("clabe ") and value.endswith(" fin")


def test_mask_does_not_mutate_input(raw_customers):
    original = dict(raw_customers[0])
    mask(original)
    assert original == raw_customers[0]


def test_unmask_returns_real_value_from_repository(repo, raw_customers):
    c = raw_customers[0]
    for field in ("clabe", "card_number", "rfc", "curp"):
        assert unmask(repo, c["id"], field) == c[field]


def test_unmask_rejects_unknown_field_or_customer(repo):
    with pytest.raises(ValueError):
        unmask(repo, "cus_001", "name")
    with pytest.raises(LookupError):
        unmask(repo, "cus_999", "clabe")
