"""07 hardening tests (impl §5 RTM). Unit-only: no Postgres/Redis/network.

Covers:
- F-HD-1 secrets prod guard + scan clean
- F-HD-2 PII allowlist/scrub + retention dry-run + live redact
- F-HD-3 audit export redaction + completeness
- F-HD-4 metrics + ledger
- F-HD-5 kill-switch flags, DLQ drain, duplicate-trigger + duplicate-execute
  idempotency, RAG-outage abstain
- F-HD-6 pilot report thresholds shape
"""
from __future__ import annotations

import asyncio
import os
import uuid

# NOTE: env is applied per-test inside the `client` fixture (with restore on
# teardown) — never at module import — so the alembic offline-render test in
# test_infra.py still sees a clean DATABASE_URL in its subprocess.

import pytest

import sys
from pathlib import Path

# tests/ convention: CWD is onboarding/ (see test_infra `from db...`).
# Ensure both `backend.*` (CWD) and `onboarding.backend.*` (repo root) resolve.
_HERE = Path(__file__).resolve()
for _cand in (_HERE.parents[1], _HERE.parents[2]):
    if str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app import jobs, llm_ledger, metrics
from backend.app.audit import write_audit
from backend.app.audit_export import check_case_completeness, export_audit_csv
from backend.app.auth import mint_dev_token
from backend.app.config import Settings
from backend.app.db import get_session
from backend.executor import (
    clear_halt,
    is_halt_requested,
)
from backend.app.main import create_app
from backend.app.models import Base
from backend.app.pii import (
    PROMPT_ALLOWLIST,
    allowlisted_hire,
    contains_pii,
    scrub_text,
)
from backend.app.retention import run_retention
from backend.app.sse import reset_bus

SERVICE = "test-service-key"

_TEST_ENV = {
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "REDIS_URL": "",
    "RAG_BASE_URL": "http://127.0.0.1:9",
    "SERVICE_API_KEY": SERVICE,
    "JWT_DEV_STUB": "true",
}


@pytest.fixture()
def client():
    saved = {k: os.environ.get(k) for k in _TEST_ENV}
    os.environ.update(_TEST_ENV)
    from backend.app.config import get_settings as _gs

    _gs.cache_clear()
    reset_bus()
    jobs.clear_enqueued()
    jobs.clear_dlq()
    metrics.reset()
    llm_ledger.reset()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = async_sessionmaker(engine, expire_on_commit=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())
    app = create_app()

    async def _override():
        async with TestSession() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        with TestClient(app, raise_server_exceptions=True) as c:
            c.test_session_factory = TestSession  # type: ignore[attr-defined]
            yield c
        asyncio.run(engine.dispose())
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _gs.cache_clear()


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _svc(suffix: str) -> dict:
    return {"X-Service-Key": SERVICE, "Idempotency-Key": f"hd-{suffix}-{uuid.uuid4().hex[:8]}"}


def _hr() -> dict:
    return {"Authorization": f"Bearer {mint_dev_token('hr_admin', 'hr-1')}"}


# --- 7.1 ---

def test_prod_guard_blocks_dev_defaults():
    bad = Settings(ENV="pilot", JWT_DEV_STUB=True, JWT_SECRET="dev-only-change-me",
                   SERVICE_API_KEY="dev-service-key")
    assert len(bad.validate_production()) >= 2
    good = Settings(ENV="pilot", JWT_DEV_STUB=False, JWT_SECRET="x" * 32,
                    SERVICE_API_KEY="y" * 32)
    assert good.validate_production() == []
    assert Settings(ENV="dev").validate_production() == []


def test_secret_scan_clean():
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "check_secrets", root / "scripts" / "check_secrets.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    findings = [f for f in mod.scan(root) if "test_hardening" not in f]
    assert findings == [], findings


# --- 7.2 ---

def test_pii_allowlist_drops_forbidden_keys():
    hire = {"name": "Anaya", "region": "UK", "national_id": "ABC123",
            "salary": "90000", "start_date": "2026-11-01"}
    out = allowlisted_hire(hire)
    assert set(out) <= set(PROMPT_ALLOWLIST)
    assert "national_id" not in out and "salary" not in out


def test_pii_scrub_shapes():
    assert "[REDACTED]" in scrub_text("SSN 123-45-6789 here")
    assert "[REDACTED]" in scrub_text("salary: 90000 paid")
    assert "[REDACTED]" in scrub_text("mail me at a@b.com")
    assert contains_pii("call +44 7700 900123")
    assert not contains_pii("hello world")


def test_retention_dry_run_then_live(client):
    from backend.app.models import ChatLog

    async def _seed():
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            old = ChatLog(employee_id="11111111-1111-4111-8111-111111111111", question="salary: 90000?",
                          answer="a@b.com", citations=[], confidence=0.9)
            from datetime import datetime, timedelta

            old.created_at = datetime.utcnow() - timedelta(days=400)
            s.add(old)
            await s.commit()
            return old.id

    cid = _run(_seed())

    async def _dry():
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            return await run_retention(s, chat_months=12, trace_months=6, dry_run=True)

    res = _run(_dry())
    assert res.chat_candidates >= 1 and res.dry_run

    async def _live():
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            out = await run_retention(s, chat_months=12, trace_months=6, dry_run=False)
            row = await s.get(ChatLog, cid)
            return out, row

    out, row = _run(_live())
    assert out.chat_redacted >= 1
    assert row.question == "[REDACTED]" and row.answer == "[REDACTED]"


def test_audit_write_scrubs_pii(client):
    async def _go():
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            row = await write_audit(s, actor="hr", event="plan.updated",
                                    entity="case:x",
                                    metadata={"note": "salary: 90000"},
                                    case_id="c1")
            return row.metadata_
    meta = _run(_go())
    assert "90000" not in str(meta)


# --- 7.3 ---

def test_audit_export_redacted_and_completeness(client):
    async def _go():
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            await write_audit(s, actor="a@b.com", event="case.triggered",
                              entity="case:c9", metadata={"idempotency_key": "k"},
                              case_id="c9", session_id="s9")
            await s.commit()
            csv_text = await export_audit_csv(s, case_id="c9")
            check = await check_case_completeness(s, "c9")
            return csv_text, check
    csv_text, check = _run(_go())
    assert "case.triggered" in csv_text
    assert "a@b.com" not in csv_text  # redacted
    assert check["events"] >= 1


def test_admin_audit_endpoints(client):
    r = client.post("/api/v1/onboarding/trigger",
                    json={"name": "N", "start_date": "2026-11-01"},
                    headers=_svc("exp"))
    assert r.status_code == 201
    case_id = r.json()["id"]
    e = client.get(f"/api/v1/admin/audit/export?case_id={case_id}", headers=_hr())
    assert e.status_code == 200 and "case.triggered" in e.text
    c = client.get(f"/api/v1/admin/audit/completeness/{case_id}", headers=_hr())
    assert c.status_code == 200 and "complete" in c.json()
    d = client.get("/api/v1/admin/retention/dry-run", headers=_hr())
    assert d.status_code == 200 and "chat_candidates" in d.json()


# --- 7.4 ---

def test_metrics_endpoint_and_chat_outcome(client):
    assert client.get("/metrics").status_code == 200
    case = client.post("/api/v1/onboarding/trigger",
                       json={"name": "M", "start_date": "2026-11-01"},
                       headers=_svc("met")).json()
    emp = {"Authorization": f"Bearer {mint_dev_token('employee', case['employee_id'])}"}
    # RAG unreachable -> abstain path still counted
    r = client.post("/api/v1/chat", json={"question": "budget?"}, headers=emp)
    assert r.status_code == 200 and r.json()["confidence"] == 0.0
    snap = metrics.snapshot()
    assert snap["chat"].get("abstained", 0) >= 1
    assert "/metrics" in client.get("/metrics").text or "onboarding_" in client.get("/metrics").text


def test_llm_ledger_cost_per_case():
    llm_ledger.reset()
    llm_ledger.record_llm_call(case_id="c1", name="chat", latency_ms=100, cost_usd=0.0, faithfulness=0.95)
    per = llm_ledger.cost_per_case()
    assert per["c1"]["calls"] == 1
    assert totals_ok()


def totals_ok() -> bool:
    return llm_ledger.totals()["calls"] >= 1


# --- 7.5 ---

def test_kill_switch_api(client):
    r = client.post("/api/v1/onboarding/trigger",
                    json={"name": "K", "start_date": "2026-11-01"},
                    headers=_svc("kill")).json()
    case_id = r["id"]
    assert client.post(f"/api/v1/admin/kill-switch/{case_id}", headers=_hr()).json()["halted"] is True
    assert is_halt_requested(case_id)
    assert client.delete(f"/api/v1/admin/kill-switch/{case_id}", headers=_hr()).json()["halted"] is False
    clear_halt(case_id)
    assert not is_halt_requested(case_id)


def test_dlq_drain_cycle(client):
    jobs.push_dlq("execute_job", "plan-1", error="boom")
    assert client.get("/api/v1/admin/dlq", headers=_hr()).json()["depth"] == 1
    assert client.post("/api/v1/admin/dlq/drain", headers=_hr()).json()["depth"] == 0


def test_duplicate_trigger_single_effect(client):
    body = {"name": "Dup", "start_date": "2026-11-01"}
    headers = _svc("dupe")
    r1 = client.post("/api/v1/onboarding/trigger", json=body, headers=headers)
    r2 = client.post("/api/v1/onboarding/trigger", json=body, headers=headers)
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


def test_duplicate_execute_single_effect():
    from backend.executor.runner import idempotency_key_for

    assert idempotency_key_for("p", 0) == idempotency_key_for("p", 0) != idempotency_key_for("p", 1)


def test_rag_outage_abstains_no_hallucination(client):
    case = client.post("/api/v1/onboarding/trigger",
                       json={"name": "R", "start_date": "2026-11-01"},
                       headers=_svc("rag")).json()
    emp = {"Authorization": f"Bearer {mint_dev_token('employee', case['employee_id'])}"}
    r = client.post("/api/v1/chat", json={"question": "What is my leave?"}, headers=emp)
    body = r.json()
    assert body["citations"] == [] and body["confidence"] == 0.0
    assert "can't answer reliably" in body["answer"] or "HR teammate" in body["answer"]


def test_readiness_gate_shape(client):
    r = client.get("/api/v1/admin/readiness", headers=_hr())
    assert r.status_code == 200
    body = r.json()
    assert {"ready", "production_blockers", "dlq_depth", "metrics"} <= set(body)
