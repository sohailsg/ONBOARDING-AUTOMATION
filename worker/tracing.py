"""Trace + cost recording (F-AG-5, 4.5). Redis publish + Langfuse cost logging."""

from __future__ import annotations

import time
from typing import Any


async def emit(session_id: str, step: str, message: str, case_id: str = "") -> dict:
    from ._compat import backend_mod

    publish = backend_mod("sse").publish
    return await publish(session_id, step, message, case_id)


class TraceRecorder:
    """Collects trace events in-memory AND fans out to SSE/redis."""

    def __init__(self, session_id: str = "", case_id: str = "") -> None:
        self.session_id = session_id
        self.case_id = case_id
        self.events: list[dict[str, Any]] = []

    async def record(self, step: str, message: str) -> dict:
        event = await emit(self.session_id, step, message, self.case_id)
        self.events.append(event)
        return event


def log_run_cost(*, tokens: int, latency_s: float, model: str,
                 case_id: str = "", session_id: str = "") -> dict[str, Any]:
    """Record per-case cost/latency. Langfuse best-effort; always returns a record.

    Ollama-local runs cost $0 — tokens/latency are still dashboarded per 4.5.
    """
    record = {"case_id": case_id, "session_id": session_id, "model": model,
              "tokens": tokens, "latency_s": round(latency_s, 3), "cost_usd": 0.0}
    try:
        from .config import get_worker_settings

        s = get_worker_settings()
        if s.langfuse_host and s.langfuse_public_key:
            import urllib.request
            import json

            body = json.dumps({"name": "plan_job", "metadata": record}).encode()
            req = urllib.request.Request(f"{s.langfuse_host.rstrip('/')}/api/public/ingestion",
                                         data=body, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=3.0):
                    pass
            except Exception:
                pass
    except Exception:
        pass
    return record
