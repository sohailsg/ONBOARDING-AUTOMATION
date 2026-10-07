"""Pure-python Okapi BM25 (app-level sparse side of hybrid search)."""
from __future__ import annotations

import math
import re

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.n = len(docs)
        self.avgdl = sum(len(d) for d in docs) / max(1, self.n)
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        self.df = df

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, query: list[str], idx: int) -> float:
        doc = self.docs[idx]
        dl = len(doc) or 1
        freq: dict[str, int] = {}
        for t in doc:
            freq[t] = freq.get(t, 0) + 1
        s = 0.0
        for t in query:
            f = freq.get(t, 0)
            if not f:
                continue
            denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
            s += self._idf(t) * f * (self.k1 + 1) / denom
        return s

    def rank(self, query_text: str) -> list[tuple[int, float]]:
        q = tokenize(query_text)
        scored = [(i, self.score(q, i)) for i in range(self.n)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


def rrf_fuse(rank_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal-rank fuse id-rankings. Returns [(id, score)] desc."""
    scores: dict[str, float] = {}
    for ranking in rank_lists:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
