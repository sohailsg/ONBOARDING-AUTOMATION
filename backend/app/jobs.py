"""Queue abstraction (jobs.py): Arq enqueue with inline/test fallback.

Worker dedupes by idempotency key; DB state is truth (at-least-once enqueue).
"""

from __future__ import annotations

import os
from typing import Any

ENQUEUED: list[dict[str, Any]] = []

# 7.5 dead-letter queue: failed jobs land here with error + attempts.
# Drained via POST /api/v1/admin/dlq/drain (SLO: <4h). In-memory for the
# single-worker pilot; mirrored to Redis list `dlq` when reachable.
DLQ: list[dict[str, Any]] = []
MAX_ATTEMPTS = 3


def _arq_redis_settings():
    """Arq CLI has no REDIS_URL override — read it here (mirrors worker/jobs)."""
    from arq.connections import RedisSettings

    url = (os.getenv("REDIS_URL", "") or "").strip()
    if url:
        try:
            return RedisSettings.from_dsn(url)
        except Exception:
            pass
    return RedisSettings()


async def enqueue(job_name: str, *args: Any, **kwargs: Any) -> str:
    """Enqueue via Arq; fall back to inline record when Redis is unavailable.

    Returns a job id (arq job id or 'inline-<n>'). Test code inspects ENQUEUED.
    """
    record: dict[str, Any] = {"job": job_name, "args": args, "kwargs": kwargs}
    try:
        from .config import get_settings

        settings = get_settings()
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        try:
            job = await pool.enqueue_job(job_name, *args, **kwargs)
            record["job_id"] = job.job_id if job else "unknown"
            ENQUEUED.append(record)
            return record["job_id"]
        finally:
            await pool.aclose()
    except Exception:
        job_id = f"inline-{len(ENQUEUED) + 1}"
        record["job_id"] = job_id
        ENQUEUED.append(record)
        return job_id


def clear_enqueued() -> None:
    ENQUEUED.clear()


def dlq_depth() -> int:
    return len(DLQ)


def dlq_entries(limit: int = 100) -> list[dict[str, Any]]:
    return list(DLQ[:limit])


def push_dlq(job_name: str, *args: Any, error: str = "", attempts: int = MAX_ATTEMPTS, **kwargs: Any) -> dict[str, Any]:
    """7.5 record a poison job. Returns the DLQ entry (audited by callers)."""
    from datetime import datetime, timezone

    entry: dict[str, Any] = {
        "job": job_name, "args": args, "kwargs": kwargs,
        "error": error[:1000], "attempts": attempts,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
    }
    DLQ.append(entry)
    try:
        from .metrics import observe_job as _observe

        _observe(job_name, "dlq")
    except Exception:
        pass
    return entry


async def drain_dlq() -> int:
    """Re-enqueue DLQ entries back to the normal queue. Returns count drained."""
    drained = 0
    while DLQ:
        entry = DLQ.pop(0)
        await enqueue(entry["job"], *entry.get("args", ()), **entry.get("kwargs", {}))
        drained += 1
    return drained


def clear_dlq() -> None:
    DLQ.clear()


# --- Arq worker entrypoints (04/05 implement bodies; gateway provides stubs) ---
async def plan_job(ctx: dict, case_id: str, session_id: str) -> dict:
    """Arq entrypoint: delegate to the worker crew (04); stub fallback if unavailable."""
    impl = _worker_plan_job()
    if impl is not None:
        return await impl(ctx, case_id, session_id)
    from .sse import publish

    await publish(session_id, "plan_queued", f"plan job queued for case {case_id}", case_id)
    return {"case_id": case_id, "session_id": session_id}


def _worker_plan_job():
    """Resolve worker.jobs.plan_job under either package root; None if unavailable."""
    try:
        from onboarding.worker.jobs import plan_job as _impl
    except ImportError:
        try:
            from worker.jobs import plan_job as _impl
        except ImportError:
            return None
    return _impl


async def execute_job(ctx: dict, plan_id: str) -> dict:
    """Arq entrypoint: deterministic post-approval execution (05-impl 5.4)."""
    try:
        from onboarding.backend.executor.runner import execute_plan
    except ImportError:  # fallback when `backend` is a top-level package
        from backend.executor.runner import execute_plan

    return await execute_plan(plan_id)


async def ingest_job(ctx: dict) -> dict:  # pragma: no cover - rag-owned
    return {"status": "queued"}


class WorkerSettings:
    functions = [plan_job, execute_job, ingest_job]
    # Same env-driven Redis as the worker package: compose maps host 6380.
    redis_settings = _arq_redis_settings()
