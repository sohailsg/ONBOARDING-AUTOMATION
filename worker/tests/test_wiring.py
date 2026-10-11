"""Backend -> worker wiring: gateway-enqueued plan_job runs the crew (04-impl §2)."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("REDIS_URL", "")

import importlib

try:
    backend_jobs = importlib.import_module("backend.app.jobs")
except ImportError:  # repo-root layout (namespace packages)
    backend_jobs = importlib.import_module("onboarding.backend.app.jobs")


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_worker_resolves_under_either_root():
    assert backend_jobs._worker_plan_job() is not None


def test_plan_job_delegates_to_worker(monkeypatch):
    calls: dict = {}

    async def _fake(ctx, case_id, session_id):
        calls["args"] = (ctx, case_id, session_id)
        return {"delegated": True, "case_id": case_id}

    monkeypatch.setattr(backend_jobs, "_worker_plan_job", lambda: _fake)
    out = _run(backend_jobs.plan_job({"job_try": 1}, "c1", "s1"))
    assert out == {"delegated": True, "case_id": "c1"}
    assert calls["args"][1:] == ("c1", "s1")


def test_plan_job_stub_fallback_without_worker(monkeypatch):
    monkeypatch.setattr(backend_jobs, "_worker_plan_job", lambda: None)
    out = _run(backend_jobs.plan_job({}, "c9", "s9"))
    assert out == {"case_id": "c9", "session_id": "s9"}
