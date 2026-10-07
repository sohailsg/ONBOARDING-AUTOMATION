"""05-impl tests: executor runner, tool wrappers, sandbox guards (impl §5 RTM).

Covers F-MCP-2 (idempotent tools), F-MCP-3 (replay+backoff), F-MCP-4
(kill switch), sandbox enforcement. SQLite-backed; no network/Redis.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app import models as m
from backend.executor import (
    HALT_REQUESTED,
    clear_halt,
    is_halt_requested,
    request_halt,
)
from backend.executor.config import (
    assert_sandbox_safe,
    assert_tool_url_allowed,
)
from backend.executor.mcp_client import FakeTransport, McpClient
from backend.executor.runner import (
    backoff_for_attempt,
    execute_plan,
    idempotency_key_for,
)
from backend.executor.tools import REGISTRY


@pytest.fixture(autouse=True)
def _clean_halt_flags():
    HALT_REQUESTED.clear()
    yield
    HALT_REQUESTED.clear()


def _mem_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _init(factory_engine):
    async with factory_engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.create_all)


async def _seed(factory, actions, case_status="executing"):
    """Seed employee + case + plan + actions. Returns (case_id, plan_id)."""
    async with factory() as s:
        emp = m.Employee(name="Anaya", role="BE", dept="Eng", region="UK", start_date=None)
        s.add(emp)
        await s.flush()
        case = m.OnboardingCase(
            employee_id=emp.id, status=case_status, current_plan_version=1,
            idempotency_key=f"test:{uuid.uuid4()}",
        )
        s.add(case)
        await s.flush()
        plan = m.Plan(case_id=case.id, version=1, json_payload={}, created_by="agent")
        s.add(plan)
        await s.flush()
        for atype, payload in actions:
            s.add(m.Action(plan_id=plan.id, type=atype, payload=payload))
        case.current_plan_version = 1
        await s.commit()
        return case.id, plan.id


async def _actions(factory, plan_id):
    async with factory() as s:
        rows = (await s.execute(select(m.Action).where(m.Action.plan_id == plan_id))).scalars().all()
        return [(a.type, a.status, a.attempts, a.external_ref) for a in rows]


# --- pure unit: backoff schedule + key format (F-MCP-3) ---


def test_backoff_schedule_is_2_10_60():
    assert [backoff_for_attempt(1), backoff_for_attempt(2), backoff_for_attempt(3)] == [2.0, 10.0, 60.0]
    assert backoff_for_attempt(9) == 60.0  # capped


def test_idempotency_key_format():
    assert idempotency_key_for("plan-1", 2) == "plan-1:2"


# --- sandbox enforcement (DoD) ---


def test_sandbox_refuses_non_loopback_tool_url():
    with pytest.raises(RuntimeError, match="sandbox"):
        assert_tool_url_allowed("https://mcp.vendor.com/rpc", "sandbox")
    assert_tool_url_allowed("http://localhost:5678/mcp", "sandbox")  # no raise


def test_sandbox_refuses_live_credentials():
    with pytest.raises(RuntimeError, match="NOTION_API_KEY"):
        assert_sandbox_safe("sandbox", {"NOTION_API_KEY": "secret"})
    assert_sandbox_safe("sandbox", {})  # no raise
    assert_sandbox_safe("live", {"NOTION_API_KEY": "secret"})  # live allows


def test_mcp_client_sandbox_requires_loopback():
    with pytest.raises(RuntimeError):
        McpClient(endpoint="https://prod.example.com/mcp", mode="sandbox")


async def test_fake_transport_echoes_idempotency_key():
    t = FakeTransport()
    client = McpClient(endpoint="http://localhost:5678/mcp", mode="sandbox", transport=t)
    res = await client.call_tool("send_email", idempotency_key="p:0", args={"to": "a@x.com"})
    assert res.external_ref == "send_email:p:0"
    assert t.calls[0]["key"] == "p:0"  # key echoed end-to-end


# --- tool wrappers: all six validate + return external_ref (F-MCP-2) ---

_VALID = {
    "send_email": {"to": "a@x.com", "subject": "s", "body": "b"},
    "post_slack": {"channel": "#c", "text": "t"},
    "create_ticket": {"queue": "IT", "title": "t", "body": "b"},
    "write_hris": {"employee_id": "e1", "fields": {"department": "Eng"}},
    "create_notion_page": {"template": "tpl", "owner": "a@x.com"},
    "create_invite": {"attendees": ["a@x.com"], "start": "2026-11-01T09:00:00Z", "end": "2026-11-01T10:00:00Z"},
}


async def test_all_wrappers_run_with_idempotency_key():
    assert set(REGISTRY) == set(_VALID)
    for name, payload in _VALID.items():
        client = McpClient(endpoint="http://localhost:5678/mcp", mode="sandbox")
        ref = await REGISTRY[name].run("plan:0", client, **payload)
        assert ref == f"{name}:plan:0"
        with pytest.raises(ValueError):
            await REGISTRY[name].run("plan:0", client)  # missing fields rejected


# --- runner: sandbox e2e success (5.6) ---


async def test_execute_plan_success_marks_case_active():
    engine, factory = _mem_factory()
    await _init(engine)
    case_id, plan_id = await _seed(factory, [
        ("send_email", {"to": "a@x.com", "subject": "s", "body": "b"}),
        ("post_slack", {"channel": "#c", "text": "t"}),
        ("create_ticket", {"queue": "IT", "title": "t", "body": "b"}),
    ])
    summary = await execute_plan(plan_id, session_factory=factory, sleep=lambda s: _nosleep(s))
    assert summary["succeeded"] == 3 and summary["failed"] == 0
    rows = await _actions(factory, plan_id)
    assert all(st == "succeeded" for _, st, _, _ in rows)
    assert all(ref == f"{t}:{plan_id}:{i}" for i, (t, _, _, ref) in enumerate(rows))
    async with factory() as s:
        case = await s.get(m.OnboardingCase, case_id)
        assert case.status == "active"
        audits = (await s.execute(select(m.AuditEvent).where(m.AuditEvent.case_id == case_id))).scalars().all()
        events = [a.event for a in audits]
        assert events.count("action.succeeded") == 3  # per-action audit (F-MCP-3/§5)
        assert "execution.completed" in events


async def _nosleep(seconds: float) -> None:
    return None


# --- runner: duplicate execute never duplicates effects (F-MCP-2/3) ---


async def test_duplicate_execute_performs_zero_tool_calls():
    engine, factory = _mem_factory()
    await _init(engine)
    _, plan_id = await _seed(factory, [("send_email", {"to": "a@x.com", "subject": "s", "body": "b"})])
    calls: list[tuple] = []

    async def counting(*, action_type, key, payload):
        calls.append((action_type, key))
        return f"{action_type}:{key}"

    first = await execute_plan(plan_id, session_factory=factory, tool_caller=counting, sleep=_nosleep)
    assert first["succeeded"] == 1 and len(calls) == 1
    second = await execute_plan(plan_id, session_factory=factory, tool_caller=counting, sleep=_nosleep)
    assert second["succeeded"] == 0 and second["skipped"] == 1 and len(calls) == 1


# --- runner: retry then success records attempts (F-MCP-3) ---


async def test_retry_then_success():
    engine, factory = _mem_factory()
    await _init(engine)
    _, plan_id = await _seed(factory, [("post_slack", {"channel": "#c", "text": "t"})])
    sleeps: list[float] = []
    state = {"n": 0}

    async def flaky(*, action_type, key, payload):
        state["n"] += 1
        if state["n"] == 1:
            raise TimeoutError("tool timeout")
        return f"{action_type}:{key}"

    async def rec_sleep(s: float) -> None:
        sleeps.append(s)

    summary = await execute_plan(plan_id, session_factory=factory, tool_caller=flaky, sleep=rec_sleep)
    assert summary["succeeded"] == 1
    assert sleeps == [2.0]  # first backoff step
    rows = await _actions(factory, plan_id)
    assert rows[0][1] == "succeeded" and rows[0][2] == 1


async def test_exhausted_retries_go_needs_attention():
    engine, factory = _mem_factory()
    await _init(engine)
    case_id, plan_id = await _seed(factory, [("post_slack", {"channel": "#c", "text": "t"})])

    async def always_fail(*, action_type, key, payload):
        raise TimeoutError("down")

    summary = await execute_plan(
        plan_id, session_factory=factory, tool_caller=always_fail, sleep=_nosleep, max_attempts=2
    )
    assert summary["failed"] == 1
    rows = await _actions(factory, plan_id)
    assert rows[0][1] == "failed" and rows[0][2] == 2
    async with factory() as s:
        assert (await s.get(m.OnboardingCase, case_id)).status == "needs_attention"


# --- runner: unknown type halts with needs_attention, no silent skip (F-MCP-4) ---


async def test_unknown_action_type_halts_remainder():
    engine, factory = _mem_factory()
    await _init(engine)
    case_id, plan_id = await _seed(factory, [
        ("send_email", {"to": "a@x.com", "subject": "s", "body": "b"}),
        ("no_such_tool", {"x": 1}),
        ("post_slack", {"channel": "#c", "text": "t"}),
    ])
    calls: list[tuple] = []

    async def counting(*, action_type, key, payload):
        calls.append((action_type, key))
        return f"{action_type}:{key}"

    summary = await execute_plan(plan_id, session_factory=factory, tool_caller=counting, sleep=_nosleep)
    assert summary["succeeded"] == 1 and summary["failed"] == 0
    rows = await _actions(factory, plan_id)
    assert rows[1][1] == "failed"  # unknown type -> failed, never silently skipped
    assert rows[2][1] == "pending"  # remainder untouched after terminal failure
    assert [c[0] for c in calls] == ["send_email"]
    async with factory() as s:
        assert (await s.get(m.OnboardingCase, case_id)).status == "needs_attention"


# --- runner: kill switch stops remainder, in-flight settles (F-MCP-4) ---


async def test_halt_mid_run_stops_remainder():
    engine, factory = _mem_factory()
    await _init(engine)
    case_id, plan_id = await _seed(factory, [
        ("send_email", {"to": "a@x.com", "subject": "s", "body": "b"}),
        ("post_slack", {"channel": "#c", "text": "t"}),
        ("create_ticket", {"queue": "IT", "title": "t", "body": "b"}),
    ])
    calls: list[str] = []

    async def halting_caller(*, action_type, key, payload):
        calls.append(action_type)
        request_halt(case_id)  # HR hits kill switch during first action
        return f"{action_type}:{key}"  # in-flight settles

    summary = await execute_plan(plan_id, session_factory=factory, tool_caller=halting_caller, sleep=_nosleep)
    assert summary["halted"] is True and calls == ["send_email"]
    rows = await _actions(factory, plan_id)
    assert rows[0][1] == "succeeded"  # in-flight settled
    assert rows[1][1] == "halted" and rows[2][1] == "halted"
    assert is_halt_requested(case_id)
    async with factory() as s:
        assert (await s.get(m.OnboardingCase, case_id)).status == "needs_attention"


# --- halt API: contract + audit (F-MCP-4) ---


def test_halt_endpoint_contract(tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.db import get_session
    from backend.app.main import create_app

    db_path = tmp_path / "halt.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    import asyncio

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(m.Base.metadata.create_all)
        async with factory() as s:
            emp = m.Employee(name="Zed", role="R", dept="D", region="UK")
            s.add(emp)
            await s.flush()
            case = m.OnboardingCase(
                employee_id=emp.id, status="executing", current_plan_version=1,
                idempotency_key=f"halt-test:{uuid.uuid4()}",
            )
            s.add(case)
            await s.flush()
            plan = m.Plan(case_id=case.id, version=1, json_payload={}, created_by="agent")
            s.add(plan)
            await s.flush()
            s.add(m.Action(plan_id=plan.id, type="send_email", payload={"to": "a@x.com"}))
            await s.commit()
            return case.id

    case_id = __import__("asyncio").run(setup())
    app = create_app()

    async def override():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(f"/api/v1/execute/{case_id}/halt", headers={"Authorization": "dev:hr_admin:alice"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["halted"] is True and body["actions_halted"] == 1 and body["case_id"] == case_id
    forbidden = client.post(f"/api/v1/execute/{case_id}/halt", headers={"Authorization": "dev:employee:bob"})
    assert forbidden.status_code == 403
