"""4.3 Sequential crew: Policy -> Experience -> Ops-Planner + retry (F-AG-4).

Live path uses CrewAI Process.sequential with output_pydantic per task.
Deterministic fallback (fixture mode / Ollama unreachable) builds the same
Pydantic outputs without an LLM so unit + integration tests stay hermetic.
Validation failure -> 1 LLM self-repair retry -> else caller marks
needs_attention (F-AG-4).
"""

from __future__ import annotations

import time
from typing import Any, Callable

from pydantic import ValidationError

from .config import get_worker_settings
from .guards import guard_tool_text
from .schemas import (
    PROMPT_VERSION,
    Entitlement,
    EntitlementSet,
    HireContext,
    Milestone,
    MilestoneItem,
    OnboardingPlan,
    SCHEMA_VERSION,
    SystemActionPlan,
    validate_full_plan,
)
from .tools import (
    BudgetExceeded,
    RunBudget,
    cache_get,
    cache_set,
    find_slots,
    new_budget,
    policy_retrieve,
)

MAX_REPAIR_RETRIES = 1
# Crew kickoff budget: generous enough for CPU-only Ollama to finish three
# sequential agent calls; the 2-min plan DoD is enforced separately on total
# run latency (PLAN_TIME_BUDGET_S in eval) so slow hardware fails honestly
# instead of aborting mid-crew.
CREW_KICKOFF_TIMEOUT_S = 300.0


# ------------------------------------------------ deterministic builders

def _kind_for(text: str) -> str:
    t = text.lower()
    if "leave" in t or "holiday" in t:
        return "leave"
    if "budget" in t or "equipment" in t or "laptop" in t:
        return "equipment_budget"
    if "training" in t or "security" in t:
        return "mandatory_training"
    return "policy"


def build_entitlements(hire: HireContext, role: str = "") -> EntitlementSet:
    cached = cache_get(hire.role or role, hire.region)
    if cached is not None:
        texts = [(c.text, c.citation) for c in cached]
        return EntitlementSet(entitlements=[
            Entitlement(kind=_kind_for(t), detail=t[:500], citation=c) for t, c in texts
        ])
    query = f"{hire.role} {hire.dept} entitlements leave equipment training"
    query, _ = guard_tool_text(query)
    chunks = policy_retrieve(query, hire.region, hire.dept)
    cache_set(hire.role or role, hire.region, chunks)
    return EntitlementSet(entitlements=[
        Entitlement(kind=_kind_for(c.text), detail=c.text[:500], citation=c.citation)
        for c in chunks
    ])


def build_plan(hire: HireContext, entitlements: EntitlementSet,
               budget: RunBudget | None = None) -> OnboardingPlan:
    attendees = [a for a in (hire.manager_id, hire.buddy_id) if a]
    window = {"start": hire.start_date, "end": hire.start_date} if hire.start_date else {}
    slots = find_slots(attendees or [hire.name], window, budget)
    budget_consume = budget.consume_step if budget else lambda *a, **k: None
    budget_consume(RunBudget.estimate_tokens(entitlements.model_dump_json()))
    meetings = [{"start": s.start, "end": s.end, "attendees": s.attendees, "status": s.status}
                for s in slots]
    training_titles = [e.detail for e in entitlements.entitlements
                       if e.kind == "mandatory_training"]
    checklist = [
        {"title": "Complete tax forms", "due_day": 1, "mandatory": True},
        {"title": training_titles[0][:120] if training_titles else "Security awareness training",
         "due_day": 1, "mandatory": True},
        {"title": "Meet buddy + manager 1:1", "due_day": 5, "mandatory": True},
        {"title": "Ship first small PR", "due_day": 7, "mandatory": False},
        {"title": "Own first feature end-to-end", "due_day": 30, "mandatory": False},
    ]
    items = [MilestoneItem.model_validate(i) for i in checklist]
    return OnboardingPlan(
        milestones=[
            Milestone(phase="Day1", items=items[:2]),
            Milestone(phase="Week1", items=items[2:4]),
            Milestone(phase="Month1", items=items[4:]),
        ],
        meetings=meetings,
        checklist=items,
    )


def build_actions(hire: HireContext, plan: OnboardingPlan, key_prefix: str) -> SystemActionPlan:
    email = f"{hire.name.lower().replace(' ', '.')}@example.com"
    start = hire.start_date or "TBD"
    tz = hire.timezone or "UTC"
    actions = [
        {"type": "send_email",
         "payload": {"to": email, "subject": f"Welcome to the team, {hire.name}!",
                     "body": f"Welcome {hire.name}! Day 1 starts {start} {tz} with your buddy."},
         "idempotency_key": f"{key_prefix}:0"},
        {"type": "create_notion_page",
         "payload": {"owner": email, "template": "eng-onboarding-v3"},
         "idempotency_key": f"{key_prefix}:1"},
        {"type": "create_invite",
         "payload": {"attendees": [email], "start": f"{start}T09:30:00", "end": f"{start}T10:00:00"},
         "idempotency_key": f"{key_prefix}:2"},
        {"type": "create_ticket",
         "payload": {"title": f"Laptop provisioning: {hire.name}", "queue": "IT",
                     "body": f"MacBook 14 + monitor for {hire.name}, start {start}"},
         "idempotency_key": f"{key_prefix}:3"},
    ]
    return SystemActionPlan.model_validate({"actions": actions})


def deterministic_payload(hire: HireContext, key_prefix: str,
                          budget: RunBudget | None = None) -> dict[str, Any]:
    entitlements = build_entitlements(hire)
    plan = build_plan(hire, entitlements, budget)
    actions = build_actions(hire, plan, key_prefix)
    payload = {"entitlements": entitlements.model_dump(), "plan": plan.model_dump(),
               "actions": actions.model_dump(),
               "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION}
    return validate_full_plan(payload).model_dump()


# ------------------------------------------------ CrewAI live path

def build_crew(hire: HireContext, llm=None, tool_set=None):
    """Build the 3-agent sequential crew (F-AG-1..3). Each task has output_pydantic."""
    from crewai import Crew, Process, Task

    from .agents.experience import build_experience_agent
    from .agents.ops import build_ops_agent
    from .agents.policy import build_policy_agent
    from .prompts import EXPERIENCE_TASK, OPS_TASK, POLICY_TASK
    from .tools import crewai_tools

    tools = tool_set if tool_set is not None else crewai_tools()
    policy_tools = [t for t in tools if getattr(t, "name", "") == "policy_retrieve"]
    slot_tools = [t for t in tools if getattr(t, "name", "") == "find_slots"]

    policy_agent = build_policy_agent(llm=llm, tools=policy_tools)
    experience_agent = build_experience_agent(llm=llm, tools=slot_tools)
    ops_agent = build_ops_agent(llm=llm)  # no tools by design (F-AG-3)

    email_hint = f"{hire.name.lower().replace(' ', '.')}@example.com"
    policy_task = Task(
        description=POLICY_TASK.format(role=hire.role, dept=hire.dept,
                                       region=hire.region, start_date=hire.start_date),
        expected_output="EntitlementSet JSON with per-item citations.",
        agent=policy_agent,
        output_pydantic=EntitlementSet,
    )
    experience_task = Task(
        description=EXPERIENCE_TASK.format(entitlements="{entitlements}", name=hire.name,
                                          role=hire.role, start_date=hire.start_date,
                                          timezone=hire.timezone or "UTC"),
        expected_output="OnboardingPlan JSON with Day1/Week1/Month1 milestones.",
        agent=experience_agent,
        context=[policy_task],
        output_pydantic=OnboardingPlan,
    )
    ops_task = Task(
        description=OPS_TASK.format(plan="{plan}", name=hire.name, email=email_hint,
                                   start_date=hire.start_date, key_prefix=hire.case_id or "plan"),
        expected_output="SystemActionPlan JSON with unique idempotency keys.",
        agent=ops_agent,
        context=[experience_task],
        output_pydantic=SystemActionPlan,
    )
    # NOTE: no max_steps kwarg — Crew has no such field (it would be silently
    # ignored). Step/token caps are enforced by RunBudget (consume_step per
    # task output), tested in test_run_plan_crew_cap_breach_terminates.
    crew = Crew(agents=[policy_agent, experience_agent, ops_agent],
                tasks=[policy_task, experience_task, ops_task],
                process=Process.sequential, verbose=False)
    return crew


async def _crew_payload(hire: HireContext, budget: RunBudget,
                        trace_cb: Callable[[str, str], Any] | None = None,
                        key_prefix: str = "",
                        timeout_s: float = CREW_KICKOFF_TIMEOUT_S,
                        repair_hint: str = "") -> dict[str, Any]:
    """Execute the CrewAI Policy -> Experience -> Ops crew (F-AG-1..4).

    Runs ``crew.kickoff()`` (blocking) in a worker thread under a timeout and
    maps the three ``output_pydantic`` task outputs to the plan payload.
    Idempotency keys are re-stamped deterministically so the executor
    contract holds regardless of LLM key formatting.

    Raises BudgetExceeded on timeout/cap breach, RuntimeError on crew/LLM
    failure or unparseable task outputs. No silent fallback here — the
    caller (run_plan_crew) decides between strict failure and the
    deterministic degraded path.
    """
    import asyncio
    import inspect as _inspect
    import json as _json

    from .llm import get_llm

    async def _emit(step: str, msg: str) -> None:
        if trace_cb is None:
            return
        res = trace_cb(step, msg)
        if _inspect.isawaitable(res):
            await res

    llm = get_llm()  # raises RuntimeError if CrewAI/LLM unavailable
    crew = build_crew(hire, llm=llm)
    if repair_hint:
        # F-AG-4 self-repair: tell the crew exactly what was rejected so the
        # retry corrects the shape instead of repeating the same output.
        note = ("\nCORRECTION — the previous output was REJECTED for: "
                + repair_hint[:800]
                + "\nOutput ONLY the required JSON shape, no other keys, no prose.")
        for task in crew.tasks:
            task.description = (task.description or "") + note
    await _emit("crew_kickoff",
                f"Running Policy->Experience->Ops crew ({llm_info_safe()})...")
    try:
        result = await asyncio.wait_for(asyncio.to_thread(crew.kickoff),
                                        timeout=timeout_s)
    except asyncio.TimeoutError as exc:
        raise BudgetExceeded(f"crew kickoff exceeded {timeout_s:g}s") from exc
    await _emit("crew_done", "Crew finished; validating structured outputs...")

    tasks_out = list(getattr(result, "tasks_output", None) or [])
    if len(tasks_out) < 3:
        raise RuntimeError(f"crew returned {len(tasks_out)} task outputs, need 3")
    prefix = key_prefix or hire.case_id or "plan"
    models: list[Any] = []
    model_classes: tuple[type[EntitlementSet], type[OnboardingPlan], type[SystemActionPlan]] = (
        EntitlementSet, OnboardingPlan, SystemActionPlan)
    for idx, (task_out, model_cls) in enumerate(zip(tasks_out[:3], model_classes)):
        pyd = getattr(task_out, "pydantic", None)
        raw = getattr(task_out, "raw", "") or ""
        if pyd is None:
            data = getattr(task_out, "json_dict", None)
            if data is None:
                try:
                    data = _json.loads(raw)
                except Exception as exc:
                    raise RuntimeError(
                        f"task {idx} output is not structured JSON") from exc
            pyd = model_cls.model_validate(data)
        budget.consume_step(RunBudget.estimate_tokens(raw))
        models.append(pyd)
    entitlements, plan, actions = models
    # Re-stamp action keys deterministically (executor contract, 05).
    for i, action in enumerate(actions.actions):
        action.idempotency_key = f"{prefix}:{i}"
    return {"entitlements": entitlements.model_dump(), "plan": plan.model_dump(),
            "actions": actions.model_dump(),
            "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION}


def llm_info_safe() -> str:
    try:
        from .llm import llm_info

        info = llm_info()
        return f"{info.get('provider')}/{info.get('model')}"
    except Exception:
        return "llm-unavailable"


async def _live_payload(hire: HireContext, budget: RunBudget,
                        trace: Callable[[str, str], Any] | None = None) -> dict[str, Any]:
    import inspect

    async def _note(step: str, msg: str) -> None:
        if trace is None:
            return
        res = trace(step, msg)
        if inspect.isawaitable(res):
            await res

    await _note("policy_retrieve", f"Searching policies for {hire.role} ({hire.region})...")
    entitlements = build_entitlements(hire)
    budget.consume_step(RunBudget.estimate_tokens(entitlements.model_dump_json()))
    await _note("experience_plan", "Building Day1/Week1/Month1 milestones + slots...")
    plan = build_plan(hire, entitlements, budget)
    await _note("ops_planner", "Proposing system actions (no side effects)...")
    actions = build_actions(hire, plan, hire.case_id or "plan")
    budget.consume_step(RunBudget.estimate_tokens(plan.model_dump_json()))
    return {"entitlements": entitlements.model_dump(), "plan": plan.model_dump(),
            "actions": actions.model_dump(),
            "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION}


async def run_plan_crew(hire: HireContext, key_prefix: str = "",
                        budget: RunBudget | None = None,
                        trace_cb: Callable[[str, str], Any] | None = None,
                        use_fixtures: bool = False,
                        strict: bool = False,
                        usage: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run Policy -> Experience -> Ops with caps + 1 self-repair retry.

    Non-fixture path executes the CrewAI crew (``crew.kickoff()``). If the
    crew/LLM fails, production falls back to the deterministic assembler so
    the <2-min schema-valid plan DoD holds without failing the job; pass
    ``strict=True`` (eval/nightly) to raise instead of degrading. ``usage``
    (optional dict) is filled with ``llm_used`` + timing/token accounting.

    Returns the validated FullPlanPayload dict. Raises ValidationError if the
    repaired output is still invalid; raises BudgetExceeded on cap breach.
    """
    from .tracing import log_run_cost

    settings = get_worker_settings()
    budget = budget or new_budget()
    t0 = time.monotonic()
    prefix = key_prefix or hire.case_id or "plan"
    attempt_payload: dict[str, Any] | None = None
    last_error: Exception | None = None
    llm_used = False

    for attempt in (0, 1):
        try:
            if use_fixtures or settings.fixture_mode == "1":
                if trace_cb is not None:
                    import inspect as _inspect

                    async def _emit(step: str, msg: str) -> None:
                        res = trace_cb(step, msg)
                        if _inspect.isawaitable(res):
                            await res

                    await _emit("policy_retrieve",
                                f"Searching policies for {hire.role} ({hire.region})...")
                    await _emit("experience_plan",
                                "Building Day1/Week1/Month1 milestones + slots...")
                    await _emit("ops_planner", "Proposing system actions (no side effects)...")
                attempt_payload = deterministic_payload(hire, prefix, budget)
                llm_used = False
            else:
                try:
                    attempt_payload = await _crew_payload(
                        hire, budget, trace_cb, key_prefix=prefix,
                        repair_hint=str(last_error)[:800] if last_error else "")
                    llm_used = True
                except BudgetExceeded:
                    raise
                except Exception as exc:
                    if strict:
                        raise
                    # Ollama/crew unreachable etc. -> deterministic fallback keeps
                    # DoD (<2 min schema-valid cited plan) without failing the job.
                    if trace_cb is not None:
                        try:
                            res = trace_cb("crew_fallback",
                                           f"Crew unavailable ({type(exc).__name__}); "
                                           f"degraded deterministic plan")
                            import inspect as _inspect2

                            if _inspect2.isawaitable(res):
                                await res
                        except Exception:
                            pass
                    attempt_payload = deterministic_payload(hire, prefix, budget)
                    llm_used = False
            validated = validate_full_plan(attempt_payload)
            latency = time.monotonic() - t0
            log_run_cost(tokens=budget.tokens, latency_s=latency,
                         model=settings.chat_model, case_id=hire.case_id,
                         session_id=hire.session_id)
            if usage is not None:
                usage.update({"llm_used": llm_used, "attempts": attempt + 1,
                              "latency_s": round(latency, 3),
                              "tokens": budget.tokens, "steps": budget.steps})
            return validated.model_dump()
        except ValidationError as exc:
            last_error = exc
            if attempt >= MAX_REPAIR_RETRIES:
                raise
            # F-AG-4 self-repair retry: loop re-runs the crew with the
            # rejection fed back as a correction hint (fixture mode rebuilds
            # deterministically) before giving up to needs_attention.
            continue
    raise last_error if last_error else ValidationError.from_exception_data("plan", [])
