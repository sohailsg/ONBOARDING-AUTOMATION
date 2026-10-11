"""Deterministic post-approval executor (05-impl, task 5.4). No LLM.

Flow (impl §2)::

    Arq execute_job(plan_id) -> execute_plan() iterates actions in order:
      skip succeeded -> tools/call {idempotency_key={plan_id}:{idx}}
      -> store external_ref -> succeeded;
      fail -> attempts++, backoff 2s/10s/60s -> needs_attention + notify;
      halt -> stop remaining.

Invariants:
- Payloads are immutable post-approval; the runner never edits ``payload``.
- Exactly-once: ``succeeded`` guard + deterministic ``{plan_id}:{idx}`` key.
  Re-running a finished plan performs zero tool calls.
- Terminal reads accept the legacy 01 DDL words (``done`` == ``succeeded``,
  ``skipped`` == ``halted``) so the runner works against both the gateway
  models (free-form status) and the Postgres CHECK-constrained DDL.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from sqlalchemy import select

from . import is_halt_requested
from .config import BACKOFF_SECONDS, MAX_ATTEMPTS, get_executor_settings
from .mcp_client import FakeTransport, McpClient
from .tools import REGISTRY

SUCCEEDED = "succeeded"
FAILED = "failed"
HALTED = "halted"
RUNNING = "running"
PENDING = "pending"

# Legacy equivalents (pre-0002 rows may still read `done`/`skipped`;
# migration 0002 widened the CHECK to the canonical words used here).
_DONE_EQUIVALENT = {"succeeded", "done"}
_HALTED_EQUIVALENT = {"halted", "skipped"}
_TERMINAL = _DONE_EQUIVALENT | {FAILED} | _HALTED_EQUIVALENT

ToolCaller = Callable[..., Awaitable[str]]
SleepFn = Callable[[float], Awaitable[None]]


def idempotency_key_for(plan_id: str, idx: int) -> str:
    return f"{plan_id}:{idx}"


def backoff_for_attempt(attempt: int) -> float:
    """attempt is 1-based count of the failure just recorded."""
    if attempt <= 0:
        return 0.0
    if attempt <= len(BACKOFF_SECONDS):
        return float(BACKOFF_SECONDS[attempt - 1])
    return float(BACKOFF_SECONDS[-1])


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _ordered_actions(rows: list[Any]) -> list[tuple[int, Any]]:
    """Deterministic execution order with stable replay.

    Primary: ``seq`` (migration 0002; assigned by PUT /plan at creation).
    Fallback for pre-0002 rows without seq: an idempotency_key of
    ``{plan_id}:{idx}`` sorts by idx; rows with neither keep fetch order.
    """
    seqs = [getattr(r, "seq", None) for r in rows]
    if rows and all(s is not None for s in seqs):
        return sorted(((int(s), r) for s, r in zip(seqs, rows) if s is not None), key=lambda t: t[0])
    keyed: list[tuple[int, Any]] = []
    unkeyed: list[Any] = []
    for row in rows:
        raw = getattr(row, "idempotency_key", None) if hasattr(row, "idempotency_key") else None
        # Gateway Action model has no idempotency_key column; fall back to
        # a per-action key inside payload (PUT /plan stores caller keys there).
        if not raw and isinstance(getattr(row, "payload", None), dict):
            raw = row.payload.get("idempotency_key")
        idx = _suffix_index(str(raw)) if raw else None
        if idx is None:
            unkeyed.append(row)
        else:
            keyed.append((idx, row))
    keyed.sort(key=lambda t: t[0])
    base = (max((i for i, _ in keyed), default=-1) + 1) if keyed else 0
    out = list(keyed)
    for n, row in enumerate(unkeyed, start=base):
        out.append((n, row))
    out.sort(key=lambda t: t[0])
    return out


def _suffix_index(raw: str) -> int | None:
    try:
        return int(raw.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        return None


async def _default_tool_caller(client: McpClient):
    async def _call(*, action_type: str, key: str, payload: dict) -> str:
        module = REGISTRY.get(action_type)
        if module is None:
            raise KeyError(f"unknown action type: {action_type}")
        return await module.run(key, client, **payload)

    return _call


async def execute_plan(
    plan_id: str,
    *,
    session_factory=None,
    tool_caller: ToolCaller | None = None,
    halt_check: Callable[[str], bool] | None = None,
    sleep: SleepFn | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    client: McpClient | None = None,
) -> dict[str, Any]:
    """Execute one approved plan. Returns a summary dict.

    Injectable seams (``session_factory``, ``tool_caller``, ``halt_check``,
    ``sleep``) exist so unit tests run without Postgres/Redis/network.
    """
    from backend.app.audit import write_audit
    from backend.app.db import get_session_factory
    from backend.app.models import Action, OnboardingCase, Plan

    settings = get_executor_settings()
    factory = session_factory or get_session_factory()
    _sleep = sleep or _default_sleep
    _client = client or McpClient(endpoint=settings.N8N_MCP_URL, mode=settings.MCP_MODE, transport=FakeTransport())
    _call = tool_caller or await _default_tool_caller(_client)
    _is_halted = halt_check or is_halt_requested

    async with factory() as session:
        plan = await session.get(Plan, plan_id)
        if plan is None:
            raise LookupError(f"plan not found: {plan_id}")
        case = await session.get(OnboardingCase, plan.case_id)
        if case is None:
            raise LookupError(f"case not found for plan: {plan_id}")

        res = await session.execute(select(Action).where(Action.plan_id == plan.id))
        rows = list(res.scalars().all())
        ordered = _ordered_actions(rows)

        # Persist deterministic keys where the column exists (replay stability).
        for idx, action in ordered:
            if hasattr(action, "idempotency_key") and not getattr(action, "idempotency_key"):
                try:
                    action.idempotency_key = idempotency_key_for(plan.id, idx)
                except Exception:
                    pass
        await session.flush()

        summary = {"plan_id": plan.id, "case_id": case.id, "succeeded": 0, "failed": 0, "skipped": 0, "halted": False}
        failed_any = False

        for idx, action in ordered:
            key = idempotency_key_for(plan.id, idx)
            status = (action.status or PENDING).strip()

            if status in _DONE_EQUIVALENT:
                summary["skipped"] += 1  # replay guard: never re-run succeeded
                continue
            if status in _HALTED_EQUIVALENT:
                summary["skipped"] += 1
                continue
            if failed_any:
                continue  # remaining stay pending after a terminal failure

            if _is_halted(case.id):
                action.status = HALTED
                action.last_error = "halt requested"
                await write_audit(
                    session, actor="system:executor", event="action.halted", entity=f"action:{action.id}",
                    metadata={"tool": action.type, "attempts": action.attempts, "idempotency_key": key},
                    case_id=case.id, session_id=case.session_id,
                )
                summary["halted"] = True
                # Mark every later pending action halted too.
                for later_idx, later in ordered:
                    if later_idx > idx and (later.status or PENDING).strip() == PENDING:
                        later.status = HALTED
                        later.last_error = "halt requested"
                break

            module = REGISTRY.get(action.type)
            if module is None:
                action.status = FAILED
                action.attempts = (action.attempts or 0) + 1
                action.last_error = f"unknown action type: {action.type}"
                failed_any = True
                await write_audit(
                    session, actor="system:executor", event="action.unknown_type", entity=f"action:{action.id}",
                    metadata={"tool": action.type, "attempts": action.attempts, "idempotency_key": key},
                    case_id=case.id, session_id=case.session_id,
                )
                continue

            action.status = RUNNING
            await session.flush()
            t0 = time.monotonic()
            try:
                payload = dict(action.payload or {})
                payload.pop("idempotency_key", None)
                external_ref = await _call(action_type=action.type, key=key, payload=payload)
            except Exception as exc:
                action.attempts = (action.attempts or 0) + 1
                action.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                action.status = FAILED if action.attempts >= max_attempts else PENDING
                latency = int((time.monotonic() - t0) * 1000)
                await write_audit(
                    session, actor="system:executor", event="action.failed", entity=f"action:{action.id}",
                    metadata={"tool": action.type, "attempts": action.attempts,
                              "external_ref": None, "latency_ms": latency,
                              "idempotency_key": key, "error": action.last_error},
                    case_id=case.id, session_id=case.session_id,
                )
                if action.status == FAILED:
                    failed_any = True
                else:
                    await session.commit()
                    await _sleep(backoff_for_attempt(action.attempts))
                    # Re-entrant retry loop for the same action (bounded).
                    while (action.attempts or 0) < max_attempts and action.status == PENDING:
                        if _is_halted(case.id):
                            break
                        t1 = time.monotonic()
                        try:
                            external_ref = await _call(action_type=action.type, key=key, payload=dict(action.payload or {}))
                        except Exception as exc2:
                            action.attempts = (action.attempts or 0) + 1
                            action.last_error = f"{type(exc2).__name__}: {exc2}"[:2000]
                            latency2 = int((time.monotonic() - t1) * 1000)
                            await write_audit(
                                session, actor="system:executor", event="action.failed",
                                entity=f"action:{action.id}",
                                metadata={"tool": action.type, "attempts": action.attempts,
                                          "external_ref": None, "latency_ms": latency2,
                                          "idempotency_key": key, "error": action.last_error},
                                case_id=case.id, session_id=case.session_id,
                            )
                            if action.attempts >= max_attempts:
                                action.status = FAILED
                                failed_any = True
                            else:
                                await session.commit()
                                await _sleep(backoff_for_attempt(action.attempts))
                            continue
                        action.status = SUCCEEDED
                        action.external_ref = external_ref
                        action.last_error = None
                        latency_ok = int((time.monotonic() - t1) * 1000)
                        await write_audit(
                            session, actor="system:executor", event="action.succeeded",
                            entity=f"action:{action.id}",
                            metadata={"tool": action.type, "attempts": action.attempts,
                                      "external_ref": external_ref, "latency_ms": latency_ok,
                                      "idempotency_key": key},
                            case_id=case.id, session_id=case.session_id,
                        )
                        break
                    if action.status == PENDING:
                        action.status = FAILED
                        failed_any = True
                summary["failed" if action.status == FAILED else "succeeded"] += 1
                await session.commit()
                continue

            action.status = SUCCEEDED
            action.external_ref = external_ref
            action.last_error = None
            latency = int((time.monotonic() - t0) * 1000)
            await write_audit(
                session, actor="system:executor", event="action.succeeded", entity=f"action:{action.id}",
                metadata={"tool": action.type, "attempts": action.attempts,
                          "external_ref": external_ref, "latency_ms": latency, "idempotency_key": key},
                case_id=case.id, session_id=case.session_id,
            )
            summary["succeeded"] += 1
            await session.commit()

        # Case-level close-out: executing -> active | needs_attention.
        await session.refresh(case)
        res2 = await session.execute(select(Action).where(Action.plan_id == plan.id))
        final_statuses = [(a.status or PENDING).strip() for a in res2.scalars().all()]
        if _is_halted(case.id) or any(s in _HALTED_EQUIVALENT for s in final_statuses):
            if case.status == "executing":
                case.status = "needs_attention"
            summary["halted"] = summary["halted"] or any(s in _HALTED_EQUIVALENT for s in final_statuses)
            await write_audit(
                session, actor="system:executor", event="execution.halted", entity=f"case:{case.id}",
                metadata={"plan_id": plan.id, **summary}, case_id=case.id, session_id=case.session_id,
            )
        elif any(s == FAILED for s in final_statuses):
            if case.status == "executing":
                case.status = "needs_attention"
            await write_audit(
                session, actor="system:executor", event="execution.needs_attention", entity=f"case:{case.id}",
                metadata={"plan_id": plan.id, **summary}, case_id=case.id, session_id=case.session_id,
            )
        elif final_statuses and all(s in _DONE_EQUIVALENT for s in final_statuses):
            if case.status == "executing":
                case.status = "active"
            await write_audit(
                session, actor="system:executor", event="execution.completed", entity=f"case:{case.id}",
                metadata={"plan_id": plan.id, **summary}, case_id=case.id, session_id=case.session_id,
            )
        await session.commit()
        return summary
