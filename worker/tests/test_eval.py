"""4.6 eval tests: grading rubric, hire generation, ledger + report gates."""

from __future__ import annotations

import asyncio
import os

os.environ["WORKER_FIXTURE_MODE"] = "1"
os.environ.setdefault("RAG_BASE_URL", "http://127.0.0.1:9")

from ..config import reset_worker_settings
from ..crew import deterministic_payload
from ..eval import (
    PLAN_TIME_BUDGET_S,
    generate_hires,
    grade_plan,
    render_report,
    run_eval,
)
from ..schemas import HireContext
from ..tools import clear_cache


def _hire() -> HireContext:
    return HireContext(name="Anaya Sharma", role="Backend Engineer", dept="Engineering",
                       region="UK", timezone="Europe/London", start_date="2026-11-01",
                       case_id="eval-case-000", session_id="eval-sess-000")


def setup_function(_):
    reset_worker_settings()
    clear_cache()


def teardown_function(_):
    reset_worker_settings()
    clear_cache()


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_grade_valid_plan_scores_high():
    grade = grade_plan(deterministic_payload(_hire(), "eval-case-000:1"))
    assert grade["checks"]["schema_valid"] == 1.0
    assert grade["citation_precision"] >= 0.9
    assert grade["score"] >= 0.9


def test_grade_invalid_plan_scores_zero():
    grade = grade_plan({"entitlements": {"entitlements": []}, "plan": {}, "actions": {}})
    assert grade["score"] == 0.0 and grade["citation_precision"] == 0.0


def test_grade_penalises_uncited_entitlement():
    payload = deterministic_payload(_hire(), "eval-case-000:1")
    # Future-dated citation: not currently effective per the F-RAG-2
    # (effective_date<=today) filter, so freshness must drop.
    payload["entitlements"]["entitlements"].append(
        {"kind": "leave", "detail": "extra day",
         "citation": {"doc": "draft-2028.pdf", "page": 1, "effective_date": "2999-01-01"}})
    grade = grade_plan(payload)
    assert grade["checks"]["citation_freshness"] < 1.0
    assert grade["citation_precision"] < 1.0


def test_generate_hires_deterministic_and_diverse():
    hires = generate_hires(20)
    assert len(hires) == 20
    assert hires == generate_hires(20)
    assert len({h.region for h in hires}) > 1
    assert len({h.role for h in hires}) > 1


def test_run_eval_ledger_rows_within_budget():
    rows = _run(run_eval(generate_hires(2), use_fixtures=True))
    assert len(rows) == 2
    for r in rows:
        assert r["error"] is None
        assert r["within_budget"] and r["seconds"] < PLAN_TIME_BUDGET_S
        assert r["citation_precision"] >= 0.9
        assert {"tokens", "steps", "checks"} <= set(r)


def test_render_report_pass_and_fail():
    rows = _run(run_eval(generate_hires(2), use_fixtures=True))
    report = render_report(rows, target=0.9)
    assert "**Verdict: PASS**" in report
    bad = [dict(rows[0], error="boom", within_budget=False,
                citation_precision=0.0, score=0.0)]
    assert "**Verdict: FAIL**" in render_report(bad, target=0.9)


def test_strict_report_fails_on_fallback_rows():
    """Nightly live gate must not pass on deterministic fallback output."""
    from ..eval import render_report

    row = {"case_id": "c", "role": "r", "region": "UK", "seconds": 10.0,
           "tokens": 100, "steps": 3, "within_budget": True, "llm_used": False,
           "citation_precision": 1.0, "score": 1.0, "checks": {}, "error": None}
    assert "FAIL" in render_report([row], strict=True)
    assert "PASS" in render_report([row], strict=False).split("Verdict:")[1]


def test_run_eval_strict_records_llm_used(monkeypatch):
    """run_eval(strict=True) surfaces crew errors instead of degrading."""
    import worker.eval as eval_mod
    from ..schemas import HireContext

    async def _boom(*a, **k):
        raise RuntimeError("ollama down")

    monkeypatch.setattr("worker.crew.run_plan_crew", _boom)
    hire = HireContext(name="n", role="r", dept="d", region="UK",
                       start_date="2026-11-01", case_id="c9", session_id="s9")
    rows = asyncio.run(eval_mod.run_eval([hire], use_fixtures=False, strict=True))
    assert rows[0]["error"] and "RuntimeError" in rows[0]["error"]
    assert rows[0]["llm_used"] is False
