"""Shared router dependencies: DB session + case/plan serialization helpers."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit
from ..auth import TokenData
from ..db import get_session
from ..models import Action, OnboardingCase, Plan as PlanRow
from ..schemas import Case, CaseStatus, Plan

Session = Depends(get_session)


def client_ip(request: Request | None) -> str:
    """Best-effort client IP for audit metadata (spec §7)."""
    if request is None:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_case_or_404(session: AsyncSession, case_id: str) -> OnboardingCase:
    case = await session.get(OnboardingCase, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")
    return case


def case_out(case: OnboardingCase) -> Case:
    return Case(
        id=case.id,
        employee_id=case.employee_id,
        status=CaseStatus(case.status),
        current_plan_version=case.current_plan_version,
        idempotency_key=case.idempotency_key,
        session_id=case.session_id,
    )


async def plan_out(session: AsyncSession, plan: PlanRow) -> Plan:
    res = await session.execute(select(Action).where(Action.plan_id == plan.id))
    rows = list(res.scalars().all())
    rows.sort(key=lambda a: (a.seq is None, a.seq if a.seq is not None else 0))
    actions = [
        {"id": a.id, "seq": a.seq, "type": a.type, "payload": a.payload, "status": a.status}
        for a in rows
    ]
    return Plan(
        id=plan.id, case_id=plan.case_id, version=plan.version, json_payload=plan.json_payload,
        created_by=plan.created_by, actions=actions,
    )


async def audit(session: AsyncSession, user: TokenData, event: str, entity: str, **kw) -> None:
    await write_audit(session, actor=f"{user.role}:{user.sub}", event=event, entity=entity, **kw)
