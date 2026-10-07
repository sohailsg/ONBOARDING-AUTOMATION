"""7.4 Langfuse per-case cost/latency ledger (spec F-HD-4).

Local stack is $0 (Ollama); the ledger keeps schema-stable cost fields so
the pilot report + Langfuse dashboard work unchanged when a paid model is
introduced. When LANGFUSE_* env is set, callers may forward these spans to
Langfuse; otherwise the in-process ledger is the source of truth.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_spans: list[dict] = []
_by_case: dict[str, dict] = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0, "latency_ms": 0.0})


def record_llm_call(
    *, case_id: str = "", name: str = "chat", latency_ms: float = 0.0,
    tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0,
    faithfulness: float | None = None,
) -> dict:
    entry = {
        "case_id": case_id, "name": name, "latency_ms": round(latency_ms, 1),
        "tokens_in": tokens_in, "tokens_out": tokens_out,
        "cost_usd": cost_usd, "faithfulness": faithfulness, "ts": time.time(),
    }
    with _lock:
        _spans.append(entry)
        agg = _by_case[case_id or "unscoped"]
        agg["calls"] += 1
        agg["cost_usd"] += cost_usd
        agg["latency_ms"] += latency_ms
        if faithfulness is not None:
            agg.setdefault("faithfulness_sum", 0.0)
            agg.setdefault("faithfulness_n", 0)
            agg["faithfulness_sum"] += faithfulness
            agg["faithfulness_n"] += 1
    return entry


def cost_per_case() -> dict[str, dict]:
    with _lock:
        out = {}
        for case_id, agg in _by_case.items():
            row = dict(agg)
            if agg.get("faithfulness_n"):
                row["avg_faithfulness"] = round(agg["faithfulness_sum"] / agg["faithfulness_n"], 3)
            out[case_id] = row
        return out


def totals() -> dict:
    with _lock:
        return {
            "calls": len(_spans),
            "cost_usd": round(sum(s["cost_usd"] for s in _spans), 4),
            "avg_latency_ms": round(sum(s["latency_ms"] for s in _spans) / len(_spans), 1) if _spans else 0.0,
        }


def reset() -> None:  # tests only
    with _lock:
        _spans.clear()
        _by_case.clear()
