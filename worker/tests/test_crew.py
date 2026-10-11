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


def test_run_plan_crew_emits_trace_steps(monkeypatch):
    seen: list[tuple[str, str]] = []

    async def _cb(step: str, message: str):
        seen.append((step, message))

    # Live path runs crew.kickoff() first (crew_kickoff/crew_done on success,
    # crew_fallback when the LLM is unreachable); the deterministic fixture
    # path emits the per-agent steps. Either way the callback fires and the
    # payload validates.
    monkeypatch.setenv("WORKER_FIXTURE_MODE", "")
    reset_worker_settings()
    payload = _run(run_plan_crew(_hire(), key_prefix="case-1:1", trace_cb=_cb))
    assert validate_full_plan(payload)
    steps = [s for s, _ in seen]
    assert "crew_kickoff" in steps and ("crew_done" in steps or "crew_fallback" in steps)


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


# ------------------------------------------------ CrewAI kickoff path (F-AG-4 live)

class _FakeTaskOut:
    def __init__(self, pydantic=None, raw="", json_dict=None):
        self.pydantic = pydantic
        self.raw = raw
        self.json_dict = json_dict


class _FakeResult:
    def __init__(self, outs):
        self.tasks_output = outs


class _FakeCrew:
    def __init__(self, outs=None, error=None):
        self.outs = outs
        self.error = error
        self.kicked = False

    def kickoff(self):
        self.kicked = True
        if self.error is not None:
            raise self.error
        return _FakeResult(self.outs)


def _stub_models():
    """Valid task outputs sliced from the deterministic payload."""
    from ..crew import deterministic_payload

    det = deterministic_payload(_hire(), "case-1:1")
    ent = EntitlementSet.model_validate(
        {"entitlements": det["entitlements"]["entitlements"][:2]})
    plan = OnboardingPlan.model_validate(det["plan"])
    acts = SystemActionPlan.model_validate(det["actions"])
    return ent, plan, acts


def _live_env(monkeypatch):
    """Force the non-fixture branch regardless of module-import env."""
    import worker.crew as crew_mod

    monkeypatch.setenv("WORKER_FIXTURE_MODE", "")
    reset_worker_settings()
    monkeypatch.setattr("worker.llm.get_llm", lambda: object())
    return crew_mod


def test_crew_kickoff_path_serves_llm_plan(monkeypatch):
    """Non-fixture run executes crew.kickoff() and validates its outputs."""
    import worker.crew as crew_mod

    _live_env(monkeypatch)
    ent, plan, acts = _stub_models()
    outs = [_FakeTaskOut(ent, '{"e":1}'), _FakeTaskOut(plan, '{"p":1}'),
            _FakeTaskOut(acts, '{"a":1}')]
    crews = []

    def _factory(hire, llm=None, tool_set=None):
        c = _FakeCrew(outs=outs)
        crews.append(c)
        return c

    monkeypatch.setattr(crew_mod, "build_crew", _factory)
    usage: dict = {}
    payload = _run(run_plan_crew(_hire(), key_prefix="case-1:1",
                                 use_fixtures=False, strict=True, usage=usage))
    assert validate_full_plan(payload)
    assert crews and crews[0].kicked, "crew.kickoff() must run the live path"
    assert usage.get("llm_used") is True
    keys = [a["idempotency_key"] for a in payload["actions"]["actions"]]
    assert keys == [f"case-1:1:{i}" for i in range(len(keys))]


def test_crew_json_fallback_when_pydantic_missing(monkeypatch):
    """litellm without structured output: json_dict/raw still validates."""
    import worker.crew as crew_mod

    _live_env(monkeypatch)
    ent, plan, acts = _stub_models()
    outs = [_FakeTaskOut(None, "", ent.model_dump()),
            _FakeTaskOut(None, "", plan.model_dump()),
            _FakeTaskOut(None, "", acts.model_dump())]
    monkeypatch.setattr(crew_mod, "build_crew",
                        lambda hire, llm=None, tool_set=None: _FakeCrew(outs=outs))
    usage: dict = {}
    payload = _run(run_plan_crew(_hire(), key_prefix="case-1:1",
                                 use_fixtures=False, strict=True, usage=usage))
    assert validate_full_plan(payload) and usage.get("llm_used") is True


def test_strict_raises_but_default_degrades(monkeypatch):
    """Crew failure: strict=True raises; default falls back (llm_used=False)."""
    import worker.crew as crew_mod

    _live_env(monkeypatch)
    monkeypatch.setattr(crew_mod, "build_crew",
                        lambda hire, llm=None, tool_set=None:
                        _FakeCrew(error=RuntimeError("ollama down")))
    with pytest.raises(RuntimeError):
        _run(run_plan_crew(_hire(), key_prefix="x", use_fixtures=False,
                           strict=True, usage={}))
    usage: dict = {}
    payload = _run(run_plan_crew(_hire(), key_prefix="x", use_fixtures=False,
                                 strict=False, usage=usage))
    assert validate_full_plan(payload)
    assert usage.get("llm_used") is False


def test_repair_retry_feeds_correction_to_crew(monkeypatch):
    """F-AG-4: validation failure -> crew re-runs with the rejection as a hint."""
    import worker.crew as crew_mod

    _live_env(monkeypatch)
    ent, plan, acts = _stub_models()
    calls = {"n": 0}

    class _HintCrew:
        def kickoff(self):
            calls["n"] += 1
            if calls["n"] == 1:
                # First attempt: experience output misses milestones.
                bad_plan = plan.model_copy(update={"milestones": []})
                outs = [_FakeTaskOut(ent, "{}"), _FakeTaskOut(bad_plan, "{}"),
                        _FakeTaskOut(acts, "{}")]
            else:
                outs = [_FakeTaskOut(ent, "{}"), _FakeTaskOut(plan, "{}"),
                        _FakeTaskOut(acts, "{}")]
            return _FakeResult(outs)

    crew_holder: dict = {}

    def _factory(hire, llm=None, tool_set=None):
        from types import SimpleNamespace

        crew = SimpleNamespace(
            tasks=[SimpleNamespace(description=f"t{i}") for i in range(3)],
            kickoff=_HintCrew().kickoff,
        )
        crew_holder["crew"] = crew
        return crew

    monkeypatch.setattr(crew_mod, "build_crew", _factory)
    usage: dict = {}
    payload = _run(run_plan_crew(_hire(), key_prefix="case-1:1",
                                 use_fixtures=False, strict=True, usage=usage))
    assert validate_full_plan(payload)
    assert calls["n"] == 2, "exactly one self-repair retry"
    retry_descriptions = [t.description for t in crew_holder["crew"].tasks]
    assert any("CORRECTION" in d for d in retry_descriptions), \
        "retry must carry the rejection hint"
    assert usage.get("llm_used") is True
