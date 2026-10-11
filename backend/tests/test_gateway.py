"""Gateway tests (02-impl §5): RBAC matrix, idempotency, SSE replay, plan/approval, scoping, chat."""

from __future__ import annotations

import asyncio
import os
import uuid

# NOTE: setdefault at import (collection-safe) + per-test override in the
# `client` fixture with restore on teardown. Unconditional assignment here
# used to clobber DATABASE_URL for infra tests sharing the pytest process.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("RAG_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SERVICE_API_KEY", "test-service-key")
os.environ.setdefault("JWT_DEV_STUB", "true")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from onboarding.backend.app import jobs
from onboarding.backend.app.auth import mint_dev_token
from onboarding.backend.app.db import get_session
from onboarding.backend.app.main import create_app
from onboarding.backend.app.models import (
    AuditEvent,
    Base,
    ChatLog,
    ChecklistItem,
    OnboardingCase,
)
from onboarding.backend.app.sse import reset_bus

SERVICE = "test-service-key"


def _key(suffix: str) -> dict:
    return {"X-Service-Key": SERVICE, "Idempotency-Key": f"test-{suffix}-{uuid.uuid4().hex[:8]}"}


def _bearer(role: str, sub: str) -> dict:
    return {"Authorization": f"Bearer {mint_dev_token(role, sub)}"}


@pytest.fixture()
def client():
    # Hermetic per-test env (sqlite + dead RAG endpoint) even when the
    # developer exported a live DATABASE_URL for infra tests; restored after.
    test_env = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "REDIS_URL": "",
        "RAG_BASE_URL": "http://127.0.0.1:9",
        "SERVICE_API_KEY": SERVICE,
        "JWT_DEV_STUB": "true",
    }
    saved = {k: os.environ.get(k) for k in test_env}
    os.environ.update(test_env)
    from onboarding.backend.app.config import get_settings as _get_settings

    _get_settings.cache_clear()
    reset_bus()
    jobs.clear_enqueued()
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
        _get_settings.cache_clear()


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _seed_case(client: TestClient, status: str = "awaiting_hr_approval") -> dict:
    """Trigger via API (service) then force status directly for deterministic tests."""

    async def _force(case_id: str):
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            case = await s.get(OnboardingCase, case_id)
            assert case is not None
            case.status = status
            await s.commit()
            return {"id": case.id, "employee_id": case.employee_id, "session_id": case.session_id}

    r = client.post(
        "/api/v1/onboarding/trigger",
        json={"name": "Test Hire", "role": "Eng", "dept": "Eng", "region": "UK", "start_date": "2026-11-01"},
        headers=_key("seed"),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    if status != "pending_ingestion":
        data.update(_run(_force(data["id"])))
    return data


# --- 2.1 scaffold: health + RBAC matrix ---


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_rbac_matrix(client):
    case = _seed_case(client)
    hr = _bearer("hr_admin", "hr-1")
    emp_headers = _bearer("employee", case["employee_id"])
    svc = {"X-Service-Key": SERVICE}
    # employee cannot trigger; service cannot list; anon gets 401
    r = client.post(
        "/api/v1/onboarding/trigger",
        json={"name": "X", "start_date": "2026-11-01"},
        headers={**emp_headers, "Idempotency-Key": "k1"},
    )
    assert r.status_code == 403
    assert client.get("/api/v1/cases", headers=svc).status_code in (401, 403)
    assert client.get("/api/v1/cases").status_code == 401
    assert client.get(f"/api/v1/cases/{case['id']}/stream").status_code == 401
    assert client.post("/api/v1/chat", json={"question": "hi"}).status_code == 401
    # hr_admin can list; employee cannot
    assert client.get("/api/v1/cases", headers=hr).status_code == 200
    assert client.get("/api/v1/cases", headers=emp_headers).status_code == 403


# --- 2.2 trigger idempotency + key validation ---


def test_trigger_idempotent_and_audit(client):
    headers = _key("idem")
    body = {"name": "Anaya", "role": "BE", "dept": "Eng", "region": "UK", "start_date": "2026-11-01"}
    r1 = client.post("/api/v1/onboarding/trigger", json=body, headers=headers)
    assert r1.status_code == 201, r1.text
    r2 = client.post("/api/v1/onboarding/trigger", json=body, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["id"] == r1.json()["id"]
    assert any(e["job"] == "plan_job" for e in jobs.ENQUEUED)

    async def _check(case_id: str):
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            rows = (await s.execute(select(AuditEvent).where(AuditEvent.case_id == case_id))).scalars().all()
            return rows

    rows = _run(_check(r1.json()["id"]))
    assert any(r.event == "case.triggered" for r in rows)


def test_validation_errors_are_400_with_details(client):
    hr = _bearer("hr_admin", "hr-1")
    # Missing required hire field.
    r = client.post(
        "/api/v1/onboarding/trigger",
        json={"role": "BE"},
        headers={"X-Service-Key": SERVICE, "Idempotency-Key": "bad-body-1"},
    )
    assert r.status_code == 400
    assert isinstance(r.json()["detail"], list)
    # Invalid status enum on list.
    assert client.get("/api/v1/cases?status=bogus", headers=hr).status_code == 400


def test_audit_metadata_has_ip_and_job_id(client):
    headers = _key("auditmeta")
    body = {"name": "Meta", "role": "BE", "dept": "Eng", "region": "UK", "start_date": "2026-11-01"}
    r = client.post("/api/v1/onboarding/trigger", json=body, headers=headers)
    assert r.status_code == 201

    async def _check(case_id: str):
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            rows = (await s.execute(select(AuditEvent).where(AuditEvent.case_id == case_id))).scalars().all()
            return {x.event: (x.metadata_ or {}) for x in rows}

    meta = _run(_check(r.json()["id"]))
    assert meta["case.triggered"]["ip"]
    assert meta["job.enqueued"]["job"] == "plan_job" and meta["job.enqueued"]["job_id"]


def test_trigger_key_validation(client):
    body = {"name": "X", "start_date": "2026-11-01"}
    r = client.post("/api/v1/onboarding/trigger", json=body, headers={"X-Service-Key": SERVICE})
    assert r.status_code == 400
    r = client.post(
        "/api/v1/onboarding/trigger", json=body,
        headers={"X-Service-Key": SERVICE, "Idempotency-Key": "k" * 129},
    )
    assert r.status_code == 400


def test_cases_list_filter_and_pagination(client):
    _seed_case(client)
    hr = _bearer("hr_admin", "hr-1")
    r = client.get("/api/v1/cases?status=awaiting_hr_approval&page=1&page_size=5", headers=hr)
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 1 and body["total"] >= 1
    assert all(c["status"] == "awaiting_hr_approval" for c in body["items"])


# --- F-API-3 SSE replay ---


@pytest.mark.asyncio
async def test_event_bus_pubsub():
    from onboarding.backend.app import sse as sse_mod

    sse_mod.reset_bus()
    q, unsub = sse_mod.subscribe_queue("sess-1")
    try:
        await sse_mod.publish("sess-1", "policy_retrieve", "hello", "case-1")
        ev = await asyncio.wait_for(q.get(), timeout=2)
        assert ev["message"] == "hello"
    finally:
        unsub()


def test_sse_reconnect_replay_live():
    """F-API-3 over real HTTP (live uvicorn): replay last-N on reconnect + live fan-out.

    NOTE: neither starlette TestClient nor httpx.ASGITransport can stream an
    infinite SSE body (both buffer until the app returns), so this spins a
    real server on loopback. All setup goes through the public API; only the
    worker-owned status step uses a direct (committed) DB tweak.
    """
    import socket
    import tempfile
    import threading
    import time

    import httpx as sync_httpx
    import uvicorn

    from onboarding.backend.app import sse as sse_mod

    sse_mod.reset_bus()
    jobs.clear_enqueued()
    fd, dbpath = tempfile.mkstemp(prefix="gw-sse-", suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{dbpath}"
    engine = create_async_engine(url, connect_args={"check_same_thread": False})
    TestSession = async_sessionmaker(engine, expire_on_commit=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run(_init())
    app = create_app()

    async def _override():
        async with TestSession() as s:
            yield s

    app.dependency_overrides[get_session] = _override

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        with sync_httpx.Client(base_url=base, timeout=10) as c:
            for _ in range(100):
                try:
                    if c.get("/health").status_code == 200:
                        break
                except Exception:
                    time.sleep(0.1)
            svc = {"X-Service-Key": SERVICE, "Idempotency-Key": f"sse-{uuid.uuid4().hex[:8]}"}
            hr = {"Authorization": f"Bearer {mint_dev_token('hr_admin', 'hr-1')}"}
            r = c.post(
                "/api/v1/onboarding/trigger",
                json={"name": "SSE Hire", "role": "E", "dept": "D", "region": "UK", "start_date": "2026-11-01"},
                headers=svc,
            )
            assert r.status_code == 201, r.text
            case = r.json()

            # Two plan versions -> two `plan.updated` audit rows (replay source).
            assert c.put(f"/api/v1/cases/{case['id']}/plan", json={"json_payload": {"a": 1}}, headers=hr).status_code == 200
            plan2 = c.put(f"/api/v1/cases/{case['id']}/plan", json={"json_payload": {"a": 2}}, headers=hr).json()

            # Worker-owned step: flip to awaiting_hr_approval (committed, short-lived conn).
            async def _force():
                async with TestSession() as s:
                    row = await s.get(OnboardingCase, case["id"])
                    assert row is not None
                    row.status = "awaiting_hr_approval"
                    await s.commit()

            _run(_force())

            with c.stream("GET", f"/api/v1/cases/{case['id']}/stream?last_n=2", headers=hr, timeout=15) as resp:
                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("text/event-stream")
                lines = resp.iter_lines()
                replay: list[str] = []
                for line in lines:
                    if line.startswith("data: "):
                        replay.append(line)
                        if len(replay) == 2:
                            break
                assert len(replay) == 2
                assert all("plan.updated" in line for line in replay)

                # Live fan-out: approve enqueues execute + publishes plan_approved.
                with sync_httpx.Client(base_url=base, timeout=10) as c2:
                    ar = c2.post(f"/api/v1/approvals/{plan2['id']}", json={"decision": "approve", "comment": "ok"}, headers=hr)
                    assert ar.status_code == 200, ar.text
                for line in lines:
                    if line.startswith("data: "):
                        assert "approved" in line
                        break
                else:
                    raise AssertionError("no live event after approve")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        _run(engine.dispose())
        try:
            os.unlink(dbpath)
        except OSError:
            pass


# --- 2.3 plan version bump + diff; approve enqueues execute ---


def test_plan_version_bump_and_diff_persisted(client):
    case = _seed_case(client)
    hr = _bearer("hr_admin", "hr-1")
    r1 = client.put(f"/api/v1/cases/{case['id']}/plan", json={"json_payload": {"a": 1}}, headers=hr)
    assert r1.status_code == 200 and r1.json()["version"] == 1
    r2 = client.put(f"/api/v1/cases/{case['id']}/plan", json={"json_payload": {"a": 2, "b": 1}}, headers=hr)
    assert r2.status_code == 200 and r2.json()["version"] == 2
    got = client.get(f"/api/v1/cases/{case['id']}/plan", headers=hr)
    assert got.json()["json_payload"] == {"a": 2, "b": 1}

    async def _check():
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            rows = (await s.execute(select(AuditEvent).where(AuditEvent.event == "plan.updated"))).scalars().all()
            return rows

    rows = _run(_check())
    assert rows and any("a" in str((r.metadata_ or {}).get("diff", "")) for r in rows)


def test_plan_duplicate_action_keys_rejected(client):
    case = _seed_case(client)
    hr = _bearer("hr_admin", "hr-1")
    body = {"json_payload": {}, "actions": [
        {"type": "x", "payload": {}, "idempotency_key": "dup"},
        {"type": "y", "payload": {}, "idempotency_key": "dup"},
    ]}
    assert client.put(f"/api/v1/cases/{case['id']}/plan", json=body, headers=hr).status_code == 400


def test_approve_enqueues_execute_and_guards(client):
    case = _seed_case(client, status="awaiting_hr_approval")
    hr = _bearer("hr_admin", "hr-1")
    plan = client.put(f"/api/v1/cases/{case['id']}/plan", json={"json_payload": {}}, headers=hr).json()
    jobs.clear_enqueued()
    r = client.post(f"/api/v1/approvals/{plan['id']}", json={"decision": "approve", "comment": "lgtm"}, headers=hr)
    assert r.status_code == 200
    assert any(e["job"] == "execute_job" for e in jobs.ENQUEUED)
    # Second approve from `executing` must 409 (status-transition guard).
    assert client.post(f"/api/v1/approvals/{plan['id']}", json={"decision": "approve"}, headers=hr).status_code == 409


def test_reject_moves_to_needs_attention(client):
    case = _seed_case(client, status="awaiting_hr_approval")
    hr = _bearer("hr_admin", "hr-1")
    plan = client.put(f"/api/v1/cases/{case['id']}/plan", json={"json_payload": {}}, headers=hr).json()
    r = client.post(f"/api/v1/approvals/{plan['id']}", json={"decision": "reject", "comment": "fix"}, headers=hr)
    assert r.status_code == 200 and r.json()["decision"] == "reject"


# --- 2.4 row scoping, checklist guards, chat ---


def _add_checklist(client: TestClient, case_id: str, title: str = "Laptop", mandatory: bool = False) -> str:
    async def _go():
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            item = ChecklistItem(case_id=case_id, title=title, due_day=1, mandatory=mandatory)
            s.add(item)
            await s.commit()
            return item.id

    return _run(_go())


def test_cross_employee_403(client):
    a = _seed_case(client)
    b = _seed_case(client)
    item_b = _add_checklist(client, b["id"])
    emp_a = _bearer("employee", a["employee_id"])
    r = client.patch(f"/api/v1/me/checklist/{item_b}", json={"completed": True}, headers=emp_a)
    assert r.status_code == 403


def test_checklist_conflict_and_mandatory_guard(client):
    case = _seed_case(client)
    emp = _bearer("employee", case["employee_id"])
    item = _add_checklist(client, case["id"], mandatory=True)
    assert client.patch(f"/api/v1/me/checklist/{item}", json={"completed": True}, headers=emp).status_code == 200
    # Optimistic-conflict: stale If-Match.
    r = client.patch(f"/api/v1/me/checklist/{item}", json={"completed": True},
                     headers={**emp, "If-Match": "null"})
    assert r.status_code == 409
    # Mandatory uncheck rejected.
    r = client.patch(f"/api/v1/me/checklist/{item}", json={"completed": False}, headers=emp)
    assert r.status_code == 409


def test_me_roadmap_forces_own_case(client):
    a = _seed_case(client)
    hr_other = _bearer("employee", "someone-else-without-case")
    assert client.get("/api/v1/me/roadmap", headers=hr_other).status_code == 404
    emp = _bearer("employee", a["employee_id"])
    assert client.get("/api/v1/me/roadmap", headers=emp).status_code == 404  # no plan yet
    hr = _bearer("hr_admin", "hr-1")
    client.put(f"/api/v1/cases/{a['id']}/plan", json={"json_payload": {"week1": ["intro"]}}, headers=hr)
    r = client.get("/api/v1/me/roadmap", headers=emp)
    assert r.status_code == 200 and r.json()["json_payload"] == {"week1": ["intro"]}


def test_chat_abstain_and_log(client):
    case = _seed_case(client)
    emp = _bearer("employee", case["employee_id"])
    r = client.post("/api/v1/chat", json={"question": "What is my budget?"}, headers=emp)
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == 0.0 and body["citations"] == []

    async def _check():
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            rows = (await s.execute(select(ChatLog))).scalars().all()
            return rows

    assert len(_run(_check())) >= 1


def test_chat_cited_path(client, monkeypatch):
    from onboarding.backend.app.routers import chat as chat_router

    async def _fake(question: str, region: str, dept: str):
        assert region == "UK"
        return {"answer": "£500 budget.", "citations": [{"doc": "policy.pdf", "page": 3}], "confidence": 0.9}

    monkeypatch.setattr(chat_router, "rag_answer", _fake)
    case = _seed_case(client)
    emp = _bearer("employee", case["employee_id"])
    r = client.post("/api/v1/chat", json={"question": "budget?"}, headers=emp)
    assert r.status_code == 200
    assert r.json()["citations"][0]["doc"] == "policy.pdf"


def test_admin_reindex_queued(client):
    hr = _bearer("hr_admin", "hr-1")
    jobs.clear_enqueued()
    r = client.post("/api/v1/admin/reindex", headers=hr)
    assert r.status_code == 202
    assert any(e["job"] == "ingest_job" for e in jobs.ENQUEUED)


def test_openapi_surface(client):
    spec = client.get("/openapi.json").json()
    for path in (
        "/api/v1/onboarding/trigger", "/api/v1/cases", "/api/v1/cases/{case_id}/stream",
        "/api/v1/cases/{case_id}/plan", "/api/v1/approvals/{plan_id}",
        "/api/v1/me/roadmap", "/api/v1/me/checklist/{item_id}",
        "/api/v1/chat", "/api/v1/admin/reindex",
    ):
        assert path in spec["paths"], path


def test_chat_rate_limit_429(client):
    """Spec 02 §3: chat 30/min/user — the 31st request in a minute is rejected."""
    from onboarding.backend.app.ratelimit import limiter

    def _reset():
        try:
            limiter._storage.reset()  # type: ignore[attr-defined]
        except Exception:
            pass

    _reset()
    try:
        case = _seed_case(client)
        # Same employee as the seeded case (server-side profile scoping).
        emp = _bearer("employee", case["employee_id"])
        codes = [
            client.post("/api/v1/chat", json={"question": f"budget q{i}?"},
                        headers=emp).status_code
            for i in range(32)
        ]
        assert codes[0] == 200
        assert codes[30] == 429, f"30/min exceeded without 429: {codes[-4:]}"
    finally:
        _reset()


def test_cases_list_tolerates_legacy_null_session_id(client):
    """Pre-0002 rows have session_id NULL — list must return them, not 500."""
    from onboarding.backend.app.models import Employee, OnboardingCase

    async def _mk():
        factory = client.test_session_factory  # type: ignore[attr-defined]
        async with factory() as s:
            s.add(Employee(id="11111111-1111-4111-8111-1111111111a1", name="Legacy Hire"))
            s.add(OnboardingCase(id="22222222-2222-4222-8222-2222222222a2",
                                 employee_id="11111111-1111-4111-8111-1111111111a1",
                                 status="active", current_plan_version=0,
                                 idempotency_key="legacy-key-1", session_id=None))
            await s.commit()

    _run(_mk())
    r = client.get("/api/v1/cases", headers=_bearer("hr_admin", "hr-1"))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["items"]]
    assert "22222222-2222-4222-8222-2222222222a2" in ids


def test_dev_login_binds_employee_and_gates_stub(client):
    """SSO-stub bridge: dev-login mints a usable credential; disabled without stub."""

    # employee -> latest hire's sub; token resolves profile (404 is
    # "no plan yet", not "no profile" — scoping works, plan doesn't exist).
    case = _seed_case(client)
    r = client.post("/api/v1/auth/dev-login", json={"role": "employee"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"].startswith("dev:employee:")
    me = client.get("/api/v1/me/roadmap",
                    headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 404 and me.json()["detail"] == "no plan yet"
    # after HR puts a plan, the same token reads the roadmap
    hr = _bearer("hr_admin", "hr-1")
    put = client.put(f"/api/v1/cases/{case['id']}/plan",
                     json={"json_payload": {"a": 1}}, headers=hr)
    assert put.status_code == 200
    me = client.get("/api/v1/me/roadmap",
                    headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200, me.text

    # hr_admin -> stable sub
    r = client.post("/api/v1/auth/dev-login", json={"role": "hr_admin"})
    assert r.json()["sub"] == "hr-1"

    # unknown employee id -> 404, not a token for nobody
    r = client.post("/api/v1/auth/dev-login",
                    json={"role": "employee",
                          "employee_id": "00000000-0000-4000-8000-000000000000"})
    assert r.status_code == 404
