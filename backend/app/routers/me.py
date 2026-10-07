"""F-API-6 employee: roadmap + checklist PATCH (row scoping, mandatory + conflict guards)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit
from ..auth import TokenData, require_roles
from ..db import get_session
from ..models import ChecklistItem, Employee, OnboardingCase, Plan
from ..schemas import ChecklistItemOut, ChecklistPatch, PlanOut
from ._shared import plan_out

router = APIRouter(prefix="/api/v1/me", tags=["me"])


async def _own_case(session: AsyncSession, user: TokenData) -> tuple[Employee, OnboardingCase]:
    """Row scoping: employee queries force employee_id = token.sub."""
    employee = await session.get(Employee, user.sub)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="employee profile not found")
    res = await session.execute(
        select(OnboardingCase).where(OnboardingCase.employee_id == employee.id).order_by(OnboardingCase.created_at.desc())
    )
    case = res.scalars().first()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no onboarding case")
    return employee, case


@router.get("/roadmap", response_model=PlanOut)
async def get_roadmap(
    user: TokenData = Depends(require_roles("employee", "hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> PlanOut:
    _, case = await _own_case(session, user)
    if case.current_plan_version <= 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no plan yet")
    res = await session.execute(
        select(Plan).where(Plan.case_id == case.id, Plan.version == case.current_plan_version)
    )
    plan = res.scalars().first()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    return await plan_out(session, plan)


@router.patch("/checklist/{item_id}", response_model=ChecklistItemOut)
async def tick_checklist(
    item_id: str,
    payload: ChecklistPatch,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: TokenData = Depends(require_roles("employee", "hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> ChecklistItemOut:
    _, case = await _own_case(session, user)
    item = await session.get(ChecklistItem, item_id)
    if item is None or item.case_id != case.id:
        # Cross-employee access collapses to 403 (must not reveal existence).
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your checklist item")
    # Optimistic-conflict path: If-Match carries last known completed_at (or "null").
    current = item.completed_at.isoformat() if item.completed_at else "null"
    if if_match is not None and if_match != current and if_match != "*":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="checklist version conflict")
    if payload.completed:
        item.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        if item.mandatory and item.completed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="mandatory task cannot be unchecked"
            )
        item.completed_at = None
    await write_audit(
        session, actor=f"{user.role}:{user.sub}", event="checklist.ticked", entity=f"checklist:{item.id}",
        metadata={"completed": payload.completed, "mandatory": item.mandatory},
        case_id=case.id, session_id=case.session_id,
    )
    await session.commit()
    return ChecklistItemOut(
        id=item.id, title=item.title, due_day=item.due_day,
        mandatory=item.mandatory, completed_at=item.completed_at,
    )
