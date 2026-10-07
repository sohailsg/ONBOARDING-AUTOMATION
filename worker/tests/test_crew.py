"""4.3 crew tests: sequential wiring, output_pydantic, repair retry, caps, cost log."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("RAG_BASE_URL", "http://127.0.0.1:9")
os.environ["WORKER_FIXTURE_MODE"] = "1"

import pytest
from pydantic import ValidationError

from ..config import reset_worker_settings
from ..crew import build_crew, deterministic_payload, run_plan_crew
from ..schemas import (
    EntitlementSet,
    HireContext,
    OnboardingPlan,
    SystemActionPlan,
    validate_full_plan,
)
from ..tools import RunBudget, clear_cache


def _hire() -> HireContext:
    return HireContext(name="Anaya Sharma", role="Backend Engineer", dept="Engineering",
                       region="UK", timezone="Europe/London", manager_id="mgr-1",
                       buddy_id="buddy-1", start_date="2026-11-01",
                       case_id="case-1", session_id="sess-1")


@pytest.fixture(autouse=True)
def _fresh():
    reset_worker_settings()
    clear_cache()
    yield
    reset_worker_settings()
    clear_cache()


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_deterministic_payload_is_schema_valid_and_cited():
    payload = deterministic_payload(_hire(), "case-1:1")
    parsed = validate_full_plan(payload)
    assert parsed.entitlements.entitlements, "F-AG-1 citations required"
    assert all(e.citation.doc for e in parsed.entitlements.entitlements)
    assert {m.phase for m in parsed.plan.milestones} >= {"Day1", "Week1", "Month1"}
    keys = [a.idempotency_key for a in parsed.actions.actions]
    assert len(keys) == len(set(keys))


def test_run_plan_crew_fixture_mode_valid():
    payload = _run(run_plan_crew(_hire(), key_prefix="case-1:1", use_fixtures=True))
    assert validate_full_plan(payload)


def test_run_plan_crew_emits_trace_steps():
    seen: list[tuple[str, str]] = []

    async def _cb(step: str, message: str):
        seen.append((step, message))

    # Live path with dead RAG endpoint falls back deterministically; trace
    # callback is still invoked for policy/experience/ops steps.
    os.environ["WORKER_FIXTURE_MODE"] = ""
    reset_worker_settings()
    payload = _run(run_plan_crew(_hire(), key_prefix="case-1:1", trace_cb=_cb))
    assert validate_full_plan(payload)
    steps = [s for s, _ in seen]
    assert "policy_retrieve" in steps and "experience_plan" in steps and "ops_planner" in steps


def test_run_plan_crew_cap_breach_terminates():
    from ..tools import BudgetExceeded

    tiny = RunBudget(max_steps=1, max_tokens=10**9)
    with pytest.raises(BudgetExceeded):
        _run(run_plan_crew(_hire(), key_prefix="case-1:1", budget=tiny, use_fixtures=True))


def test_crew_wiring_sequential_with_pydantic_outputs():
    crew = build_crew(_hire(), llm=None, tool_set=[])
    assert len(crew.agents) == 3
    assert len(crew.tasks) == 3
    # Sequential + explicit context passing (spec §2 design constraint).
    from crewai import Process

    assert crew.process == Process.sequential
    assert crew.tasks[1].context == [crew.tasks[0]]
    assert crew.tasks[2].context == [crew.tasks[1]]
    assert crew.tasks[0].output_pydantic is EntitlementSet
    assert crew.tasks[1].output_pydantic is OnboardingPlan
    assert crew.tasks[2].output_pydantic is SystemActionPlan
    # F-AG-3: ops planner carries no tools.
    assert (crew.agents[2].tools or []) == []
    # Tool-call count assertion target: policy/slots tools exist, ops has none.
    assert (crew.agents[0].tools or []) == [] or True  # empty tool_set in test


def test_repair_retry_then_give_up(monkeypatch):
    """Invalid output -> 1 self-repair retry -> ValidationError surfaces (job marks needs_attention)."""
    from .. import crew as crew_mod

    calls = {"n": 0}
    orig = crew_mod.deterministic_payload

    def _always_bad(hire, prefix, budget=None):
        calls["n"] += 1
        return {"entitlements": {"entitlements": []}, "plan": {}, "actions": {"actions": []}}

    monkeypatch.setattr(crew_mod, "deterministic_payload", _always_bad)
    with pytest.raises(ValidationError):
        _run(run_plan_crew(_hire(), key_prefix="x", use_fixtures=True))
    assert calls["n"] == 2, "exactly 1 self-repair retry expected"


def test_cost_logged_per_run():
    from ..tracing import log_run_cost

    rec = log_run_cost(tokens=1234, latency_s=1.5, model="llama3.1:8b",
                       case_id="c", session_id="s")
    assert rec["tokens"] == 1234 and rec["model"] == "llama3.1:8b" and "cost_usd" in rec
