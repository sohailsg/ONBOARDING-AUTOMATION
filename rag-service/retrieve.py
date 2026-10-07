"""Hybrid retrieve (task 3.2): pre-filter → dense + BM25 → RRF → rerank → top-5 → parent-expand.

Internal contract: ``retrieve(query, region, dept, k=30) ->
chunks[{text, doc, page, effective_date, score}]``.

Filters (F-RAG-2, enforced in code — never in the prompt):
``region == user.region AND (dept == all OR == user.dept)
AND effective_date <= today AND superseded_by IS NULL``.
"""
from __future__ import annotations

import datetime as dt

from bm25 import BM25, rrf_fuse, tokenize
from config import SETTINGS
from rerank import rerank as _rerank


def retrieve(
    query: str,
    region: str,
    dept: str,
    k: int = 30,
    *,
    store=None,
    embed_backend=None,
    rerank_top_k: int = 0,
    today: str = "",
) -> list[dict]:
    from vector_store import PolicyStore

    store = store or PolicyStore(
        persist_dir=SETTINGS.chroma_dir, collection=SETTINGS.collection
    )
    today = today or dt.date.today().isoformat()
    top_k = k or SETTINGS.hybrid_top_k
    final_k = rerank_top_k or SETTINGS.rerank_top_k

    # -- embed query (degrade: hash backend works offline) -----------------
    try:
        if embed_backend is None:
            import embeddings as _emb

            embed_backend = _emb.get_backend(
                SETTINGS.embedding_backend, SETTINGS.ollama_host, SETTINGS.embed_model
            )
        q_emb = embed_backend.embed([query])[0]
    except Exception:
        q_emb = None

    # -- dense side --------------------------------------------------------
    dense_rank: list[str] = []
    by_id: dict[str, dict] = {}
    if q_emb is not None:
        try:
            for r in store.dense_query(q_emb, region, dept, today, n_results=top_k):
                r["dense_score"] = max(0.0, 1.0 - float(r.get("distance", 1.0)))
                by_id[r["chunk_id"]] = r
                dense_rank.append(r["chunk_id"])
        except Exception:
            pass

    # -- sparse side (app-level BM25 over the filtered corpus) -------------
    try:
        corpus = store.filtered_corpus(region, dept, today)
    except Exception:
        corpus = []
    for c in corpus:
        by_id.setdefault(c["chunk_id"], c)
    bm25_rank: list[str] = []
    if corpus:
        tokenized = [tokenize(c.get("text", "")) for c in corpus]
        bm25 = BM25(tokenized)
        for idx, s in bm25.rank(query)[:top_k]:
            cid = corpus[idx]["chunk_id"]
            by_id[cid]["bm25"] = float(s)
            bm25_rank.append(cid)

    if not by_id:
        return []

    # -- RRF fuse ------------------------------------------------------------
    fused = rrf_fuse(
        [r for r in (dense_rank, bm25_rank) if r], k=SETTINGS.rrf_k
    )
    if not fused:
        # no dense signal (e.g. empty index side) — fall back to BM25 order
        fused = [(cid, 0.0) for cid in bm25_rank] or [
            (cid, 0.0) for cid in dense_rank
        ]
    candidates = []
    for cid, fscore in fused[: max(top_k, final_k * 4)]:
        c = dict(by_id[cid])
        c["fused_score"] = float(fscore)
        candidates.append(c)

    # -- rerank → top-5 --------------------------------------------------------
    try:
        ranked = _rerank(query, candidates, query_embedding=q_emb)
    except Exception:
        ranked = sorted(candidates, key=lambda x: x.get("fused_score", 0.0), reverse=True)
    top = ranked[:final_k]

    # -- parent-expand ----------------------------------------------------------
    expanded: list[dict] = []
    seen: set[str] = set()
    for c in top:
        expanded.append(_public(c))
        seen.add(c["chunk_id"])
        pid = c.get("parent_id") or ""
        if pid and pid not in seen:
            try:
                parent = store.get_parent(pid)
            except Exception:
                parent = None
            if parent and parent.get("text"):
                expanded.append(
                    {
                        "text": parent["text"],
                        "doc": parent.get("document_name", c.get("document_name", "")),
                        "page": int(parent.get("page", c.get("page", 0)) or 0),
                        "effective_date": parent.get(
                            "effective_date", c.get("effective_date", "")
                        ),
                        "score": float(c.get("rerank_score", c.get("fused_score", 0.0))),
                        "chunk_id": pid,
                        "parent_expanded": True,
                    }
                )
                seen.add(pid)
    return expanded


def _public(c: dict) -> dict:
    return {
        "text": c.get("text", ""),
        "doc": c.get("document_name", c.get("doc", "")),
        "page": int(c.get("page", 0) or 0),
        "effective_date": c.get("effective_date", ""),
        "score": float(c.get("rerank_score", c.get("fused_score", 0.0))),
        "chunk_id": c.get("chunk_id", ""),
    }
