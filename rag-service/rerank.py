"""Rerank: local cross-encoder when available, lexical fallback otherwise.

Free-stack binding: ``RERANK_MODEL=sentence-transformers/ms-marco-MiniLM-L-6-v2``
— used if ``sentence_transformers`` is installed; otherwise a deterministic
BM25 + cosine blend reranker (no downloads, CI-safe). Both expose
``rerank(query, chunks) -> chunks`` with ``rerank_score`` set.
"""
from __future__ import annotations

import os

from bm25 import tokenize
from embeddings import cosine


def _lexical_rerank(query: str, chunks: list[dict]) -> list[dict]:
    qtok = set(tokenize(query))
    for c in chunks:
        ctok = tokenize(c.get("text", ""))
        overlap = len(qtok & set(ctok)) / max(1, len(qtok))
        c["rerank_score"] = 0.5 * float(c.get("bm25", 0.0) > 0) * min(
            1.0, float(c.get("bm25", 0.0)) / 5.0
        ) + 0.5 * overlap
        # blend dense cosine signal when present
        dense = c.get("dense_score")
        if isinstance(dense, (int, float)):
            c["rerank_score"] = 0.6 * c["rerank_score"] + 0.4 * max(0.0, min(1.0, dense))
    chunks.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    return chunks


class CrossEncoderReranker:
    def __init__(self, model_name: str = "") -> None:
        from sentence_transformers import CrossEncoder  # type: ignore

        self.model = CrossEncoder(
            model_name or os.getenv("RERANK_MODEL", "sentence-transformers/ms-marco-MiniLM-L-6-v2")
        )

    def rerank(self, query: str, chunks: list[dict]) -> list[dict]:
        pairs = [(query, c.get("text", "")) for c in chunks]
        scores = self.model.predict(pairs)
        for c, s in zip(chunks, scores):
            c["rerank_score"] = float(s)
        chunks.sort(key=lambda x: x["rerank_score"], reverse=True)
        return chunks


def rerank(query: str, chunks: list[dict], query_embedding=None) -> list[dict]:
    """Rerank chunks in place (adds ``rerank_score``). Never raises."""
    if not chunks:
        return chunks
    try:
        from sentence_transformers import CrossEncoder  # noqa: F401

        return CrossEncoderReranker().rerank(query, chunks)
    except Exception:
        pass
    # cosine assist when query embedding + chunk embeddings known
    if query_embedding is not None:
        for c in chunks:
            emb = c.get("embedding")
            if emb is not None:
                try:
                    c["dense_score"] = cosine(list(query_embedding), list(emb))
                except Exception:
                    pass
    return _lexical_rerank(query, chunks)
