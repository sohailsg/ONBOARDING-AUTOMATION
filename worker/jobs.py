"""4.4 Arq plan_job: status machine, versioned insert, traces, audit.

Flow: set agent_processing -> Policy(policy_retrieve) -> Experience(find_slots)
-> Ops-Planner(no tools) -> validate -> INSERT plans(version+1,
created_by='agent') + draft checklist_items -> set awaiting_hr_approval ->
publish traces per step to trace:{session_id} + audit_events.

Validation failure -> 1 self-repair retry (in crew) -> else needs_attention.
Poison job -> DLQ after N attempts with needs_attention.
Duplicate job -> dedupe (return existing plan) — one job per case semantics.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

MAX_JOB_TRIES = 3


def _arq_redis_settings():
    """Arq has no REDIS_URL env override — read it here so non-default ports
    (compose maps host 6380) work. Empty/unparseable falls back to localhost."""
    from arq.connections import RedisSettings

    url = (os.getenv("REDIS_URL", "") or "").strip()
    if url:
        try:
            return RedisSettings.from_dsn(url)
        except Exception:
            pass
    return RedisSettings()


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _set_status(session, case, to: str, *, actor: str = "agent:plan_crew",
                      session_id: str = "", event: str = "case.status_changed") -> None:
    from ._compat import backend_mod

    write_audit = backend_mod("audit").write_audit
    can_transition = backend_mod("models").can_transition

    frm = case.status
    if frm == to:
        return
    if not can_transition(frm, to):
        raise RuntimeError(f"illegal status transition {frm!r} -> {to!r}")
    case.status = to
    await session.flush()
    await write_audit(session, actor=actor, event=event, entity=f"case:{case.id}",
                      metadata={"from": frm, "to": to},
                      case_id=case.id, session_id=session_id)


def _hire_context(case, employee) -> Any:
    from .schemas import HireContext

    start = employee.start_date.isoformat() if getattr(employee, "start_date", None) else ""
    if hasattr(start, "isoformat"):
        start = start.isoformat()
    return HireContext(
        name=employee.name, role=employee.role or "", dept=employee.dept or "",
        region=employee.region or "", timezone=employee.timezone or "",
        manager_id=employee.manager_id, buddy_id=employee.buddy_id,
        start_date=str(start or ""), case_id=case.id, session_id=case.session_id,
    )


async def plan_job(ctx: dict, case_id: str, session_id: str,
                   _session_factory=None, _use_fixtures: bool = False) -> dict:
    """Arq entrypoint. Returns {case_id, plan_id, version, status}."""
    from sqlalchemy import select

    from ._compat import backend_mod

    audit_mod = backend_mod("audit")
    models_mod = backend_mod("models")
    sse_mod = backend_mod("sse")
    write_audit = audit_mod.write_audit
    ChecklistItem, Employee, OnboardingCase, Plan = (
        models_mod.ChecklistItem, models_mod.Employee,
        models_mod.OnboardingCase, models_mod.Plan,
    )
    Action = models_mod.Action
    publish = sse_mod.publish

    from .crew import run_plan_crew
    from .schemas import PRE_APPROVAL_STATUSES
    from .tools import BudgetExceeded, new_budget
    from .tracing import TraceRecorder

    if _session_factory is None:
        from ._compat import backend_mod

        _session_factory = backend_mod("db").get_session_factory()

    job_try = 0
    try:
        job_try = int((ctx or {}).get("job_try", 1))
    except Exception:
        job_try = 1

    trace = TraceRecorder(session_id=session_id, case_id=case_id)
    budget = new_budget()

    async with _session_factory() as session:
        case = await session.get(OnboardingCase, case_id)
        if case is None:
            await publish(session_id, "plan_failed", f"case {case_id} not found", case_id)
            return {"case_id": case_id, "status": "not_found"}

        # ---- dedupe: planning already produced a versioned plan
        if case.status not in PRE_APPROVAL_STATUSES and case.current_plan_version > 0:
            existing = await session.execute(
                select(Plan).where(Plan.case_id == case_id,
                                   Plan.version == case.current_plan_version))
            row = existing.scalars().first()
            await publish(session_id, "plan_deduped",
                          f"plan v{case.current_plan_version} already exists for case {case_id}",
                          case_id)
            return {"case_id": case_id, "plan_id": row.id if row else None,
                    "version": case.current_plan_version, "status": case.status,
                    "deduped": True}

        # ---- poison pill: too many attempts -> DLQ as needs_attention
        if job_try > MAX_JOB_TRIES:
            try:
                await _set_status(session, case, "needs_attention", session_id=session_id,
                                  event="plan.poison_pill")
            except RuntimeError:
                case.status = "needs_attention"
            await write_audit(session, actor="agent:plan_crew", event="plan.poison_pill",
                              entity=f"case:{case_id}",
                              metadata={"job_try": job_try}, case_id=case_id, session_id=session_id)
            await session.commit()
            await publish(session_id, "plan_failed",
                          f"plan job for case {case_id} sent to DLQ after {job_try} tries", case_id)
            return {"case_id": case_id, "status": "needs_attention", "dlq": True}

        # ---- enter agent_processing
        try:
            await _set_status(session, case, "agent_processing", session_id=session_id)
            await session.commit()
        except RuntimeError:
            await session.rollback()
            return {"case_id": case_id, "status": case.status}
        await trace.record("agent_processing", f"plan job started for case {case_id}")
        await write_audit(session, actor="agent:plan_crew", event="plan.started",
                          entity=f"case:{case_id}", metadata={"job_try": job_try},
                          case_id=case_id, session_id=session_id)
        await session.commit()

        employee = await session.get(Employee, case.employee_id)
        if employee is None:
            await _set_status(session, case, "needs_attention", session_id=session_id,
                              event="plan.missing_employee")
            await session.commit()
            await publish(session_id, "plan_failed", f"employee missing for case {case_id}", case_id)
            return {"case_id": case_id, "status": "needs_attention"}

        hire = _hire_context(case, employee)
        key_prefix = f"{case_id}:{case.current_plan_version + 1}"

        async def _trace_cb(step: str, message: str) -> None:
            await trace.record(step, message)
            await write_audit(session, actor="agent:plan_crew", event=f"plan.{step}",
                              entity=f"case:{case_id}", metadata={"message": message[:500]},
                              case_id=case_id, session_id=session_id)

        try:
            usage: dict = {}
            payload = await run_plan_crew(hire, key_prefix=key_prefix, budget=budget,
                                          trace_cb=_trace_cb, use_fixtures=_use_fixtures,
                                          usage=usage)
            llm_used = bool(usage.get("llm_used", False))
        except BudgetExceeded as exc:
            await _set_status(session, case, "needs_attention", session_id=session_id,
                              event="plan.cap_exceeded")
            await write_audit(session, actor="agent:plan_crew", event="plan.cap_exceeded",
                              entity=f"case:{case_id}", metadata={"error": str(exc),
                                                                  "budget": budget.snapshot()},
                              case_id=case_id, session_id=session_id)
            await session.commit()
            await publish(session_id, "plan_failed",
                          f"plan for case {case_id} hit run caps ({exc}); flagged for HR", case_id)
            return {"case_id": case_id, "status": "needs_attention", "error": str(exc)}
        except Exception as exc:  # validation still failing after repair, or unexpected
            try:
                await _set_status(session, case, "needs_attention", session_id=session_id,
                                  event="plan.validation_failed")
            except RuntimeError:
                case.status = "needs_attention"
            await write_audit(session, actor="agent:plan_crew", event="plan.validation_failed",
                              entity=f"case:{case_id}",
                              metadata={"error": f"{type(exc).__name__}: {exc}"[:1000]},
                              case_id=case_id, session_id=session_id)
            await session.commit()
            await publish(session_id, "plan_failed",
                          f"plan for case {case_id} needs attention: {type(exc).__name__}", case_id)
            return {"case_id": case_id, "status": "needs_attention",
                    "error": f"{type(exc).__name__}: {exc}"[:500]}

        # ---- persist: plans(version+1) + draft checklist_items
        new_version = (case.current_plan_version or 0) + 1
        plan_row = Plan(case_id=case_id, version=new_version,
                        json_payload=payload, created_by="agent")
        plan_row.id = str(uuid.uuid4())
        session.add(plan_row)
        await session.flush()

        checklist = payload.get("plan", {}).get("checklist", []) or []
        for item in checklist:
            session.add(ChecklistItem(case_id=case_id, title=str(item.get("title", ""))[:300],
                                     due_day=int(item.get("due_day", 1)),
                                     mandatory=bool(item.get("mandatory", False))))
        # Materialize executor rows (05 reads actions table, not the payload).
        for i, a in enumerate(payload.get("actions", {}).get("actions", []) or []):
            session.add(Action(plan_id=plan_row.id, seq=i, type=str(a.get("type", "")),
                               payload=dict(a.get("payload", {}) or {}), status="pending",
                               attempts=0, idempotency_key=a.get("idempotency_key")))
        case.current_plan_version = new_version
        await session.flush()
        await write_audit(session, actor="agent:plan_crew", event="plan.created",
                          entity=f"plan:{plan_row.id}",
                          metadata={"version": new_version, "steps": budget.steps,
                                    "tokens": budget.tokens, "prompt_version": payload.get("prompt_version"),
                                    "llm_used": llm_used},
                          case_id=case_id, session_id=session_id)

        await _set_status(session, case, "awaiting_hr_approval", session_id=session_id,
                          event="plan.ready_for_review")
        await write_audit(session, actor="agent:plan_crew", event="plan.ready_for_review",
                          entity=f"plan:{plan_row.id}", metadata={"version": new_version},
                          case_id=case_id, session_id=session_id)
        await session.commit()

        await trace.record("plan_ready",
                           f"plan v{new_version} ready for HR review (case {case_id})")
        return {"case_id": case_id, "plan_id": plan_row.id, "version": new_version,
                "status": "awaiting_hr_approval", "steps": budget.steps, "tokens": budget.tokens,
                "llm_used": llm_used}


class WorkerSettings:  # Arq discovers `functions`
    functions = [plan_job]
    redis_settings = _arq_redis_settings()

    @staticmethod
    async def on_startup(ctx: dict) -> None:  # drain-safe defaults
        ctx["started_at"] = _now_naive().isoformat()
