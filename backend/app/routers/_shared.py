"""Shared router dependencies: DB session + case/plan serialization helpers."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit
from ..auth import TokenData
from ..db import get_session
from ..models import Action, OnboardingCase, Plan
from ..schemas import CaseOut, PlanOut

Session = Depends(get_session)


async def get_case_or_404(session: AsyncSession, case_id: str) -> OnboardingCase:
    case = await session.get(OnboardingCase, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")
    return case


def case_out(case: OnboardingCase) -> CaseOut:
    return CaseOut(
        id=case.id,
        employee_id=case.employee_id,
        status=case.status,
        current_plan_version=case.current_plan_version,
        idempotency_key=case.idempotency_key,
        session_id=case.session_id,
    )


async def plan_out(session: AsyncSession, plan: Plan) -> PlanOut:
    res = await session.execute(select(Action).where(Action.plan_id == plan.id))
    actions = [
        {"id": a.id, "type": a.type, "payload": a.payload, "status": a.status} for a in res.scalars().all()
    ]
    return PlanOut(
        id=plan.id, case_id=plan.case_id, version=plan.version, json_payload=plan.json_payload,
        created_by=plan.created_by, actions=actions,
    )


async def audit(session: AsyncSession, user: TokenData, event: str, entity: str, **kw) -> None:
    await write_audit(session, actor=f"{user.role}:{user.sub}", event=event, entity=entity, **kw)
