"""Policy retrieval (spec 03): BM25 over section chunks, with a no-support threshold.

- One chunk per `##` section; id `doc_id#section-slug`, stable across runs. The text
  keeps HTML comments on purpose: a poisoned instruction reaches the index like any
  real compromised document would, and the defense lives in the validator (spec 05).
- Every result is masked and wrapped as untrusted (source "politica").
- Safe failure: if no chunk clears the threshold, the result is an explicit `[]` and the
  agent says it found no support. It never falls back to a "best guess".
"""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from backend.security.masking import Json, mask
from backend.security.untrusted import wrap_untrusted

DEFAULT_POLICIES_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"
SOURCE = "politica"
MAX_K = 5
K1, B = 1.5, 0.75
# Calibrated with the spec 03 tests and frozen (optimistic by construction: the same
# queries tune and test it). Lowest relevant expected chunk: 2.519; highest unrelated
# top-1: 1.710 ("personas" matches "persona de operaciones"). Margins: -0.519 / +0.290.
# Real measurement: retrieval recall in the evals runner (spec 04).
SCORE_THRESHOLD = 2.0

STOPWORDS = frozenset(
    """
    a al algo ante antes aun aunque como con contra cual cuando de del desde donde dos
    e el ella ellas ello ellos en entre era es esa esas ese eso esos esta estan estas este
    esto estos fue fui ha hace hay hasta la las le les lo los mas me mi mis mucho muy nada
    ni no nos o otra otro para pero poco por porque que quien se sea si sin sobre solo son
    su sus tambien te tiene todo todos tu tus un una uno unos unas y ya yo
    """.split()
)


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    terms: tuple[str, ...]


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _fold(text)).strip("-")


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", _fold(text)) if w not in STOPWORDS]


def _chunks_of(doc: Path) -> list[Chunk]:
    parts = re.split(r"^## +(.+?)\s*$", doc.read_text(encoding="utf-8"), flags=re.MULTILINE)
    chunks = []
    # parts = [preamble, title1, body1, title2, body2, ...]; the preamble is not indexed.
    for title, body in zip(parts[1::2], parts[2::2], strict=True):
        text = f"## {title}\n{body.strip()}"
        chunks.append(Chunk(f"{doc.stem}#{_slug(title)}", text, tuple(tokenize(text))))
    return chunks


class PolicyIndex:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = tuple(chunks)
        self._tf = [Counter(c.terms) for c in self.chunks]
        self._avgdl = sum(len(c.terms) for c in self.chunks) / len(self.chunks)
        df = Counter(term for c in self.chunks for term in set(c.terms))
        n = len(self.chunks)
        self._idf = {t: math.log((n - f + 0.5) / (f + 0.5) + 1) for t, f in df.items()}

    def scores(self, query: str) -> list[tuple[float, Chunk]]:
        terms = tokenize(query)
        scored = []
        for chunk, tf in zip(self.chunks, self._tf, strict=True):
            dl = len(chunk.terms)
            score = 0.0
            for term in terms:
                f = tf.get(term, 0)
                if f:
                    norm = f + K1 * (1 - B + B * dl / self._avgdl)
                    score += self._idf[term] * f * (K1 + 1) / norm
            scored.append((score, chunk))
        # Stable order: score desc, then id.
        return sorted(scored, key=lambda sc: (-sc[0], sc[1].id))


def build_index(policies_dir: Path = DEFAULT_POLICIES_DIR) -> PolicyIndex:
    return PolicyIndex([c for doc in sorted(policies_dir.glob("*.md")) for c in _chunks_of(doc)])


@cache
def _default_index() -> PolicyIndex:
    return build_index()


def search_policies(
    query: str, k: int = 3, index: PolicyIndex | None = None
) -> list[dict[str, Any]]:
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be between 1 and {MAX_K}")
    results: list[dict[str, Json]] = []
    for score, chunk in (index or _default_index()).scores(query)[:k]:
        # score > 0 implies at least one non-stopword query term matched.
        if score <= 0 or score < SCORE_THRESHOLD:
            break
        wrapped = wrap_untrusted(chunk.text, SOURCE)
        result: dict[str, Json] = {
            "id": chunk.id,
            "score": round(score, 4),
            "text": {"untrusted_text": wrapped["untrusted_text"], "source": wrapped["source"]},
        }
        # Whole result through mask(): the text and also the id (built from a title).
        results.append(mask(result))
    return [dict(r) for r in results]
