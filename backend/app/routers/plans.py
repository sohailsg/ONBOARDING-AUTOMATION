"""F-API-4 plan GET/PUT: version bump + diff persisted to audit metadata."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit
from ..auth import TokenData, require_roles
from ..db import get_session
from ..models import Action, OnboardingCase, Plan
from ..schemas import PlanIn, PlanOut
from ._shared import get_case_or_404, plan_out

router = APIRouter(prefix="/api/v1/cases", tags=["plans"])


def _diff(old: dict, new: dict, path: str = "") -> list[dict]:
    changes: list[dict] = []
    for key in sorted(set(old) | set(new)):
        p = f"{path}.{key}" if path else str(key)
        if key not in old:
            changes.append({"path": p, "op": "added", "new": new[key]})
        elif key not in new:
            changes.append({"path": p, "op": "removed", "old": old[key]})
        elif isinstance(old[key], dict) and isinstance(new[key], dict):
            changes.extend(_diff(old[key], new[key], p))
        elif old[key] != new[key]:
            changes.append({"path": p, "op": "changed", "old": old[key], "new": new[key]})
    return changes


@router.get("/{case_id}/plan", response_model=PlanOut)
async def get_plan(
    case_id: str,
    user: TokenData = Depends(require_roles("hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> PlanOut:
    case = await get_case_or_404(session, case_id)
    if case.current_plan_version <= 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no plan yet")
    res = await session.execute(
        select(Plan).where(Plan.case_id == case.id, Plan.version == case.current_plan_version)
    )
    plan = res.scalars().first()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    return await plan_out(session, plan)


@router.put("/{case_id}/plan", response_model=PlanOut)
async def update_plan(
    case_id: str,
    payload: PlanIn,
    user: TokenData = Depends(require_roles("hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> PlanOut:
    case = await get_case_or_404(session, case_id)
    prev_payload: dict = {}
    if case.current_plan_version > 0:
        res = await session.execute(
            select(Plan).where(Plan.case_id == case.id, Plan.version == case.current_plan_version)
        )
        prev = res.scalars().first()
        if prev is not None:
            prev_payload = prev.json_payload or {}
    # Idempotency-key uniqueness guard for action payloads (sample_plan fixture invariant).
    keys = [a.idempotency_key for a in payload.actions if a.idempotency_key]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="duplicate action idempotency keys")

    new_version = case.current_plan_version + 1
    plan = Plan(case_id=case.id, version=new_version, json_payload=payload.json_payload, created_by="hr_user")
    session.add(plan)
    await session.flush()
    for a in payload.actions:
        session.add(Action(plan_id=plan.id, type=a.type, payload=a.payload or {}))
    diff = _diff(prev_payload, payload.json_payload or {})
    case.current_plan_version = new_version
    await write_audit(
        session, actor=f"{user.role}:{user.sub}", event="plan.updated", entity=f"plan:{plan.id}",
        metadata={"case_id": case.id, "version": new_version, "diff": diff, "diff_paths": [d["path"] for d in diff]},
        case_id=case.id, session_id=case.session_id,
    )
    await session.commit()
    return await plan_out(session, plan)
