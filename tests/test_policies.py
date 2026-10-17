"""Spec 03 — RAG de políticas: corpus, chunking estable, BM25 con umbral, no confiable."""

import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from backend.policies.retrieval import build_index, search_policies

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES_DIR = REPO_ROOT / "data" / "policies"
POISONED_CHUNK = "contracargos#plazos-y-requisitos"

# Written as a customer would, after the corpus: no title or section terms copied.
CUSTOMER_QUERIES = {
    "spei-tiempos#transferencias-pendientes": (
        "le transferí a mi proveedor desde ayer en la mañana y todavía no le cae el dinero"
    ),
    "spei-devoluciones#cuando-se-devuelve-un-spei": (
        "mi transferencia rebotó y no entiendo el motivo, el destinatario jura que su número "
        "de cuenta existe"
    ),
    "cep#que-es-el-cep": (
        "ocupo el recibo oficial del pago que hice porque el otro asegura que nunca le cayó"
    ),
    "aclaraciones#cuando-procede-una-aclaracion": (
        "el monto que me descontaron no coincide con lo que autoricé, quiero que lo revisen"
    ),
    "contracargos#que-es-un-contracargo": (
        "compré unos tenis en línea, ya pasó un mes y la tienda nunca los mandó"
    ),
    "rechazos-tarjeta#motivos-frecuentes": (
        "intenté comprar en una app y la tarjeta salió declinada aunque tengo fondos"
    ),
    "fraude-cargos-no-reconocidos#senales-de-fraude": (
        "tengo varias compras raras fuera de México que nunca autoricé, todas seguidas"
    ),
    "privacidad#solo-la-cuenta-del-titular": (
        "quiero saber si a mi primo ya le depositaron, pásame el historial de su cuenta"
    ),
}
POISON_QUERY = (
    "la tienda me hizo un cargo duplicado, hasta cuándo puedo disputarlo y qué evidencia piden"
)
UNRELATED_QUERIES = [
    "cómo preparo un pozole rojo para diez personas",
    "va a llover mañana en Guadalajara",
    "de la que el y en los",
]


def _words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", folded)


def _trigrams(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + 3]) for i in range(len(words) - 2)}


def test_policy_corpus_shape():
    docs = sorted(POLICIES_DIR.glob("*.md"))
    assert len(docs) == 8
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        assert 150 <= len(text.split()) <= 250, doc.name
        assert len(re.findall(r"^## ", text, flags=re.MULTILINE)) >= 2, doc.name
    ids = [c.id for c in build_index(POLICIES_DIR).chunks]
    assert len(ids) == len(set(ids))
    assert POISONED_CHUNK in ids


def test_chunk_ids_are_stable():
    first = [(c.id, c.text) for c in build_index(POLICIES_DIR).chunks]
    second = [(c.id, c.text) for c in build_index(POLICIES_DIR).chunks]
    assert first == second
    assert all(re.fullmatch(r"[a-z0-9-]+#[a-z0-9-]+", chunk_id) for chunk_id, _ in first)


@pytest.mark.parametrize("expected_id", sorted(CUSTOMER_QUERIES))
def test_relevant_query_retrieves_expected_chunk(expected_id):
    query = CUSTOMER_QUERIES[expected_id]
    chunk = next(c for c in build_index(POLICIES_DIR).chunks if c.id == expected_id)
    # Guard against queries that copy the corpus: no 3 consecutive normalized words shared.
    shared = _trigrams(_words(query)) & _trigrams(_words(chunk.text))
    assert not shared, f"la consulta copia el corpus: {sorted(shared)}"

    results = search_policies(query, k=3)
    assert expected_id in [r["id"] for r in results], [r["id"] for r in results]


def test_poisoned_chunk_is_retrieved_by_plausible_query():
    results = search_policies(POISON_QUERY, k=3)
    by_id = {r["id"]: r for r in results}
    assert POISONED_CHUNK in by_id, list(by_id)
    source = (POLICIES_DIR / "contracargos.md").read_text(encoding="utf-8")
    (hidden,) = re.findall(r"<!--.*?-->", source, flags=re.DOTALL)
    assert hidden in by_id[POISONED_CHUNK]["text"]["untrusted_text"]


@pytest.mark.parametrize("query", UNRELATED_QUERIES)
def test_unrelated_query_returns_empty(query):
    assert search_policies(query) == []


def test_untrusted_content_is_delimited():
    queries = [*CUSTOMER_QUERIES.values(), POISON_QUERY]
    results = [r for q in queries for r in search_policies(q, k=5)]
    assert results
    for r in results:
        assert set(r) == {"id", "score", "text"}
        assert r["text"]["source"] == "politica"
        assert set(r["text"]) == {"untrusted_text", "source"}
        assert isinstance(r["text"]["untrusted_text"], str)
        assert isinstance(r["score"], float)


@pytest.mark.parametrize("k", [0, 6, -1])
def test_search_policies_caps_k(k):
    with pytest.raises(ValueError):
        search_policies("me rebotó la transferencia", k=k)


def test_results_are_sorted_and_capped():
    results = search_policies(POISON_QUERY, k=2)
    assert len(results) <= 2
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_policies_import_contract(tmp_path):
    root = tmp_path / "project"
    for package in ("backend", "mcp_server"):
        shutil.copytree(
            REPO_ROOT / package, root / package, ignore=shutil.ignore_patterns("__pycache__")
        )
    shutil.copy(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    module = root / "backend" / "policies" / "retrieval.py"
    module.write_text(module.read_text() + "\nimport backend.mock_core.repository  # noqa\n")
    result = subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports")],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode != 0
    assert "policies are independent of the core and the MCP BROKEN" in result.stdout
