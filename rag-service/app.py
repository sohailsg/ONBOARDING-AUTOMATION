"""RAG service HTTP API (FastAPI).

Endpoints:
  GET  /health
  POST /retrieve      -> hybrid retrieve (internal: chat API 02, policy tool 04)
  POST /answer        -> answer from provided chunks
  POST /chat          -> retrieve + answer in one call (Flow C)
  POST /rag/reindex   -> lifecycle webhook {doc_id, version} (task 3.4)
  POST /api/v1/admin/reindex -> alias of the above (gateway forwards here)

Degrades to abstain (never hallucinate) when the index is unavailable.
"""
from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException

import observability as obs
from answer import answer as answer_fn
from config import SETTINGS
from models import (
    AnswerRequest,
    ChatRequest,
    ChatResponse,
    Citation,
    ReindexRequest,
    RetrievedChunk,
    RetrieveRequest,
    RetrieveResponse,
)
from retrieve import retrieve as retrieve_fn

app = FastAPI(title="RAG service (free/local)", version="1.0.0")


@app.get("/health")
def health() -> dict:
    try:
        from vector_store import PolicyStore

        count = PolicyStore(
            persist_dir=SETTINGS.chroma_dir, collection=SETTINGS.collection
        ).count()
    except Exception:
        count = -1
    return {
        "ok": True,
        "collection": SETTINGS.collection,
        "points": count,
        "embed_model": SETTINGS.embed_model,
        "chat_model": SETTINGS.chat_model,
    }


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve_ep(req: RetrieveRequest) -> RetrieveResponse:
    try:
        chunks = retrieve_fn(req.query, req.region, req.dept, k=req.k)
    except Exception:
        chunks = []
    return RetrieveResponse(chunks=[RetrievedChunk(**c) for c in chunks])


@app.post("/answer", response_model=ChatResponse)
def answer_ep(req: AnswerRequest) -> ChatResponse:
    res = answer_fn(req.query, [c.model_dump() for c in req.chunks])
    return ChatResponse(
        answer=res["answer"],
        citations=[Citation(**c) for c in res["citations"]],
        confidence=res["confidence"],
        abstained=res["abstained"],
    )


@app.post("/chat", response_model=ChatResponse)
def chat_ep(req: ChatRequest) -> ChatResponse:
    t0 = time.perf_counter()
    try:
        chunks = retrieve_fn(req.question, req.region or "UK", req.dept or "all")
    except Exception:
        chunks = []
    try:
        res = answer_fn(req.question, chunks)
    except Exception:
        res = {
            "answer": SETTINGS.abstain_text,
            "citations": [],
            "confidence": 0.0,
            "abstained": True,
        }
    obs.query_log(
        query=req.question,
        region=req.region,
        dept=req.dept,
        latency_ms=(time.perf_counter() - t0) * 1000,
        num_candidates=len(chunks),
        rerank_scores=[c.get("score", 0.0) for c in chunks],
        confidence=res["confidence"],
        abstained=res["abstained"],
    )
    return ChatResponse(
        answer=res["answer"],
        citations=[Citation(**c) for c in res["citations"]],
        confidence=res["confidence"],
        abstained=res["abstained"],
    )


def _do_reindex(req: ReindexRequest) -> dict:
    if not req.doc_id or not req.path or not req.region or not req.effective_date:
        raise HTTPException(
            status_code=422,
            detail="doc_id, path, region and effective_date are required",
        )
    from lifecycle import reindex as reindex_fn

    try:
        return reindex_fn(
            req.path,
            doc_id=req.doc_id,
            region=req.region,
            department=req.department,
            effective_date=req.effective_date,
            version=req.version,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"reindex failed: {e}")


@app.post("/rag/reindex")
def reindex_ep(req: ReindexRequest) -> dict:
    return _do_reindex(req)


@app.post("/api/v1/admin/reindex")
def admin_reindex_ep(req: ReindexRequest) -> dict:
    return {"enqueued": True, **_do_reindex(req)}
