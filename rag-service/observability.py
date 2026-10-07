"""Observability: per-query log + Langfuse stub (wired, off by default).

Every retrieval/answer call emits ``query_log`` with latency, k values,
rerank scores, confidence, abstain flag. Langfuse tracing activates only when
``LANGFUSE_HOST + PUBLIC_KEY + SECRET_KEY`` are all set (W7); otherwise no-op.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager

log = logging.getLogger("rag-service")


def langfuse_enabled() -> bool:
    return bool(
        os.getenv("LANGFUSE_HOST", "")
        and os.getenv("LANGFUSE_PUBLIC_KEY", "")
        and os.getenv("LANGFUSE_SECRET_KEY", "")
    )


@contextmanager
def trace(name: str, **attrs):
    """No-op span unless Langfuse is configured (avoids hard dep)."""
    start = time.perf_counter()
    try:
        yield {"name": name, **attrs}
    finally:
        dur_ms = (time.perf_counter() - start) * 1000
        log.info("trace name=%s duration_ms=%.1f attrs=%s", name, dur_ms, attrs)


def query_log(
    *,
    query: str,
    region: str,
    dept: str,
    latency_ms: float,
    num_candidates: int,
    rerank_scores: list[float],
    confidence: float,
    abstained: bool,
) -> dict:
    entry = {
        "query": query[:500],
        "region": region,
        "dept": dept,
        "latency_ms": round(latency_ms, 1),
        "num_candidates": num_candidates,
        "rerank_scores": [round(float(s), 3) for s in rerank_scores[:5]],
        "confidence": confidence,
        "abstained": abstained,
        # cost: local stack = $0; record zeros so dashboards stay schema-stable
        "cost_usd": 0.0,
        "embed_model": os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        "chat_model": os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b"),
    }
    log.info("rag_query %s", entry)
    return entry
