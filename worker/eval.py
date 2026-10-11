"""4.6 HR citation-quality pass + nightly e2e scoring (04-impl task 4.6, §5 eval).

Automated proxy for the HR grading session: every generated plan is scored
on citation presence/freshness, schema validity, milestone sense,
action idempotency, and injection-freedom. HR still grades a sample by hand
(citation *relevance* needs a human); this harness produces the pre-scored
report + JSONL ledger (timing/tokens per case) that the session starts from.

DoD gates asserted per plan: schema-valid cited plan in <~2 min.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

from .guards import contains_injection
from .schemas import HireContext

GRADE_TARGET = 0.9  # default; HR confirms the final target in the grading session
PLAN_TIME_BUDGET_S = 120.0  # impl §3 DoD: valid cited plan <~2 min


def grade_plan(payload: dict[str, Any]) -> dict[str, Any]:
    """Score a plan payload dict. Returns {checks: {...}, citation_precision, score}."""
    checks: dict[str, float] = {}
    try:
        from .schemas import validate_full_plan

        parsed = validate_full_plan(payload)
        checks["schema_valid"] = 1.0
    except Exception:
        return {"checks": {"schema_valid": 0.0}, "citation_precision": 0.0, "score": 0.0}

    ents = parsed.entitlements.entitlements
    with_cite = [e for e in ents
                 if e.citation.doc and e.citation.page and e.citation.effective_date]
    checks["citation_presence"] = len(with_cite) / max(1, len(ents))
    today = date.today().isoformat()
    fresh = [e for e in with_cite
             if (e.citation.effective_date or "") <= today and (e.citation.page or 0) >= 1]
    checks["citation_freshness"] = len(fresh) / max(1, len(ents))
    checks["injection_free"] = (
        0.0 if any(contains_injection(e.detail) for e in ents) else 1.0
    )

    phases = {m.phase for m in parsed.plan.milestones}
    checks["milestones_sensible"] = (
        1.0 if {"Day1", "Week1", "Month1"} <= phases else 0.0
    )
    checks["checklist_sensible"] = (
        1.0 if parsed.plan.checklist and all(
            1 <= i.due_day <= 90 and i.title for i in parsed.plan.checklist
        ) else 0.0
    )
    keys = [a.idempotency_key for a in parsed.actions.actions]
    checks["actions_idempotent"] = (
        1.0 if keys and len(keys) == len(set(keys)) else 0.0
    )
    meetings = parsed.plan.meetings or []
    wellformed = [m for m in meetings
                  if m.get("status") in ("confirmed", "tbd")
                  and (m.get("status") != "confirmed" or m.get("start") != "TBD")]
    checks["no_invented_meetings"] = len(wellformed) / max(1, len(meetings)) if meetings else 1.0

    citation_precision = (checks["citation_presence"] + checks["citation_freshness"]
                          + checks["injection_free"]) / 3.0
    score = sum(checks.values()) / len(checks)
    return {"checks": checks, "citation_precision": round(citation_precision, 3),
            "score": round(score, 3)}


_HIRE_POOL = [
    ("Anaya Sharma", "Backend Engineer", "Engineering", "UK", "Europe/London"),
    ("Bruno Costa", "Frontend Engineer", "Engineering", "UK", "Europe/London"),
    ("Chloe Dubois", "Product Designer", "Design", "UK", "Europe/Paris"),
    ("Dev Patel", "Data Analyst", "Analytics", "US", "America/New_York"),
    ("Elena Rossi", "QA Engineer", "Engineering", "DE", "Europe/Berlin"),
    ("Farid Khan", "DevOps Engineer", "Engineering", "UK", "Europe/London"),
    ("Grace Liu", "Support Specialist", "Support", "US", "America/Chicago"),
    ("Hugo Meyer", "Backend Engineer", "Engineering", "DE", "Europe/Berlin"),
    ("Ivy Chen", "HR Coordinator", "People", "UK", "Europe/London"),
    ("Jonas Weber", "Frontend Engineer", "Engineering", "DE", "Europe/Berlin"),
]


def generate_hires(n: int, start_date: str = "2026-11-01") -> list[HireContext]:
    """Deterministic diversified hires for the grading set (cycles the pool)."""
    hires: list[HireContext] = []
    for i in range(max(1, n)):
        name, role, dept, region, tz = _HIRE_POOL[i % len(_HIRE_POOL)]
        hires.append(HireContext(
            name=name if n <= len(_HIRE_POOL) else f"{name} {i // len(_HIRE_POOL) + 1}",
            role=role, dept=dept, region=region, timezone=tz,
            start_date=start_date, case_id=f"eval-case-{i:03d}",
            session_id=f"eval-sess-{i:03d}"))
    return hires


async def run_eval(hires: list[HireContext], use_fixtures: bool = True,
                   strict: bool = False) -> list[dict[str, Any]]:
    """Generate + grade one plan per hire. Returns ledger rows (timing/tokens/grade).

    ``strict=True`` (nightly --live) fails loudly instead of silently
    degrading: crew/LLM errors propagate as row errors and rows record
    ``llm_used=False`` whenever the deterministic fallback served.
    """
    from .crew import run_plan_crew
    from .tools import new_budget

    rows: list[dict[str, Any]] = []
    for hire in hires:
        budget = new_budget()
        usage: dict[str, Any] = {}
        t0 = time.monotonic()
        try:
            payload = await run_plan_crew(hire, key_prefix=f"{hire.case_id}:1",
                                          budget=budget, use_fixtures=use_fixtures,
                                          strict=strict, usage=usage)
            error: str | None = None
        except Exception as exc:  # noqa: BLE001 — ledger records failures
            payload, error = {}, f"{type(exc).__name__}: {exc}"[:300]
        dt = time.monotonic() - t0
        grade = grade_plan(payload) if payload else {
            "checks": {"schema_valid": 0.0}, "citation_precision": 0.0, "score": 0.0}
        rows.append({"case_id": hire.case_id, "role": hire.role, "region": hire.region,
                     "seconds": round(dt, 2), "tokens": budget.tokens, "steps": budget.steps,
                     "within_budget": dt < PLAN_TIME_BUDGET_S,
                     "llm_used": bool(usage.get("llm_used", False)),
                     "citation_precision": grade["citation_precision"],
                     "score": grade["score"], "checks": grade["checks"], "error": error})
    return rows


def render_report(rows: list[dict[str, Any]], target: float = GRADE_TARGET,
                   strict: bool = False) -> str:
    """Markdown HR sign-off report (4.6): pre-scored table + gate verdict.

    ``strict=True`` additionally requires every row to have come from the
    LLM crew (``llm_used``) — the nightly live gate must not pass on
    deterministic fallback output.
    """
    import datetime

    n = len(rows) or 1
    avg_prec = sum(r["citation_precision"] for r in rows) / n
    avg_score = sum(r["score"] for r in rows) / n
    slow = [r["case_id"] for r in rows if not r["within_budget"]]
    failed = [r["case_id"] for r in rows if r["error"]]
    degraded = [r["case_id"] for r in rows if not r.get("llm_used", False)]
    gate = avg_prec >= target and not slow and not failed
    if strict:
        gate = gate and not degraded
    strict_tag = " (strict)" if strict else " (info)"
    degraded_txt = "PASS" if not degraded else "FAIL " + str(degraded)
    lines = [
        f"# Worker citation-quality report ({datetime.date.today().isoformat()})",
        "",
        f"- Plans graded: **{len(rows)}** (target set: 20 for the HR session)",
        f"- Mean citation precision: **{avg_prec:.3f}** (target ≥ {target})",
        f"- Mean plan score: **{avg_score:.3f}**",
        f"- LLM-crew served: **{n - len(degraded)}/{n}**",
        f"- Over 2-min budget: {slow or 'none'}",
        f"- Failures: {failed or 'none'}",
        "",
        "## Gate",
        f"- Citation precision ≥ target: {'PASS' if avg_prec >= target else 'FAIL'}",
        f"- All plans <2 min: {'PASS' if not slow else 'FAIL'}",
        f"- Zero failures: {'PASS' if not failed else 'FAIL'}",
        f"- All plans LLM-served{strict_tag}: {degraded_txt}",
        "",
        f"**Verdict: {'PASS' if gate else 'FAIL'}**",
        "",
        "## Per-plan scores",
        "",
        "| case | role | region | secs | tokens | cite_prec | score | error |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['case_id']} | {r['role']} | {r['region']} | {r['seconds']} "
                     f"| {r['tokens']} | {r['citation_precision']} | {r['score']} "
                     f"| {r['error'] or ''} |")
    lines += ["",
              "HR hand-grade: sample 3+ plans for citation *relevance* (automation checks",
              "presence/freshness only), then sign here: HR ___  date ___"]
    return "\n".join(lines) + "\n"
