"""4.4 integration: plan_job full run (status + version + traces + audit), dedupe, caps."""

from __future__ import annotations

import asyncio
import os
import uuid

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = ""
os.environ["RAG_BASE_URL"] = "http://127.0.0.1:9"
os.environ["WORKER_FIXTURE_MODE"] = "1"

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from .._compat import backend_mod
from ..config import reset_worker_settings
from ..jobs import WorkerSettings, plan_job
from ..tools import clear_cache

_models = backend_mod("models")
_sse = backend_mod("sse")
_audit = backend_mod("audit")

Base = _models.Base
Employee, OnboardingCase, Plan = _models.Employee, _models.OnboardingCase, _models.Plan
ChecklistItem, AuditEvent = _models.ChecklistItem, _models.AuditEvent


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run(_init())
    return async_sessionmaker(engine, expire_on_commit=False), engine


def _seed(factory, status="pending_ingestion"):
    async def _go():
        async with factory() as s:
            emp = Employee(name="Anaya Sharma", role="Backend Engineer",
                           dept="Engineering", region="UK", timezone="Europe/London",
                           manager_id=None, buddy_id=None)
            try:
                from datetime import date

                emp.start_date = date(2026, 11, 1)
            except Exception:
                pass
            s.add(emp)
            await s.flush()
            case = OnboardingCase(employee_id=emp.id, status=status,
                                  current_plan_version=0,
                                  idempotency_key=f"plan-test-{uuid.uuid4().hex[:8]}",
                                  session_id=f"sess-{uuid.uuid4().hex[:8]}")
            s.add(case)
            await s.commit()
            return case.id, case.session_id

    return _run(_go())


def setup_function(_):
    reset_worker_settings()
    clear_cache()
    _sse.reset_bus()


def teardown_function(_):
    reset_worker_settings()
    clear_cache()
    _sse.reset_bus()


def test_worker_settings_registers_plan_job():
    assert plan_job in WorkerSettings.functions
    import inspect

    sig = inspect.signature(plan_job)
    assert list(sig.parameters)[:3] == ["ctx", "case_id", "session_id"]


def test_plan_job_full_run_status_version_traces_audit():
    factory, engine = _factory()
    try:
        case_id, session_id = _seed(factory)
        q, _unsub = _sse.subscribe_queue(session_id)
        try:
            out = _run(plan_job({"job_try": 1}, case_id, session_id,
                                _session_factory=factory, _use_fixtures=True))
        finally:
            pass
        assert out["status"] == "awaiting_hr_approval", out
        assert out["version"] == 1 and out["plan_id"]

        async def _check():
            async with factory() as s:
                case = await s.get(OnboardingCase, case_id)
                plans = (await s.execute(select(Plan).where(Plan.case_id == case_id))).scalars().all()
                items = (await s.execute(
                    select(ChecklistItem).where(ChecklistItem.case_id == case_id))).scalars().all()
                audits = (await s.execute(
                    select(AuditEvent).where(AuditEvent.case_id == case_id))).scalars().all()
                return case, plans, items, audits

        case, plans, items, audits = _run(_check())
        assert case.status == "awaiting_hr_approval"
        assert case.current_plan_version == 1
        assert len(plans) == 1 and plans[0].created_by == "agent"
        payload = plans[0].json_payload
        assert set(payload) >= {"entitlements", "plan", "actions"}
        assert all(e["citation"]["doc"] for e in payload["entitlements"]["entitlements"])
        assert items, "draft checklist_items expected"
        assert any(a.event == "plan.created" for a in audits)
        assert any(a.event == "plan.ready_for_review" for a in audits)
        # SSE traces visible (F-AG-5).
        assert not q.empty()
    finally:
        _run(engine.dispose())


def test_plan_job_duplicate_deduped():
    factory, engine = _factory()
    try:
        case_id, session_id = _seed(factory)
        first = _run(plan_job({"job_try": 1}, case_id, session_id,
                              _session_factory=factory, _use_fixtures=True))
        assert first["status"] == "awaiting_hr_approval"
        second = _run(plan_job({"job_try": 1}, case_id, session_id,
                               _session_factory=factory, _use_fixtures=True))
        assert second.get("deduped") is True
        assert second["version"] == 1

        async def _count():
            async with factory() as s:
                rows = (await s.execute(select(Plan).where(Plan.case_id == case_id))).scalars().all()
                return len(rows)

        assert _run(_count()) == 1
    finally:
        _run(engine.dispose())


def test_plan_job_invalid_output_marks_needs_attention(monkeypatch):
    from .. import crew as crew_mod

    async def _boom(*args, **kwargs):
        from pydantic import ValidationError

        raise ValidationError.from_exception_data("plan", [
            {"type": "missing", "loc": ("entitlements",), "msg": "broken", "input": {}}])

    monkeypatch.setattr(crew_mod, "run_plan_crew", _boom)
    factory, engine = _factory()
    try:
        case_id, session_id = _seed(factory)
        out = _run(plan_job({"job_try": 1}, case_id, session_id,
                            _session_factory=factory, _use_fixtures=True))
        assert out["status"] == "needs_attention"

        async def _check():
            async with factory() as s:
                case = await s.get(OnboardingCase, case_id)
                audits = (await s.execute(
                    select(AuditEvent).where(AuditEvent.case_id == case_id))).scalars().all()
                return case.status, [a.event for a in audits]

        status, events = _run(_check())
        assert status == "needs_attention"
        assert "plan.validation_failed" in events
    finally:
        _run(engine.dispose())


def test_plan_job_poison_pill_to_dlq():
    factory, engine = _factory()
    try:
        case_id, session_id = _seed(factory, status="agent_processing")
        out = _run(plan_job({"job_try": 99}, case_id, session_id,
                            _session_factory=factory, _use_fixtures=True))
        assert out["status"] == "needs_attention" and out.get("dlq") is True
    finally:
        _run(engine.dispose())
