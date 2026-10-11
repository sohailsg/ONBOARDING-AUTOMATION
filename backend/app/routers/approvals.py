"""F-API-5 approvals: record decision; approve enqueues execute job."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from .. import jobs
from ..audit import write_audit
from ..auth import TokenData, require_roles
from ..db import get_session
from ..models import Approval as ApprovalRow, OnboardingCase, Plan as PlanRow, can_transition
from ..schemas import Approval, ApprovalDecision
from ._shared import client_ip

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


@router.post("/{plan_id}", response_model=Approval)
async def decide_approval(
    plan_id: str,
    payload: ApprovalDecision,
    request: Request,
    user: TokenData = Depends(require_roles("hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> Approval:
    plan = await session.get(PlanRow, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    case = await session.get(OnboardingCase, plan.case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")

    if payload.decision == "approve":
        if case.status != "awaiting_hr_approval":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot approve from status {case.status}",
            )
        target = "executing"
        if not can_transition(case.status, target):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="illegal status transition")
        case.status = target
        approval = ApprovalRow(plan_id=plan.id, approver_id=user.sub, decision="approve", comment=payload.comment or "")
        session.add(approval)
        await write_audit(
            session, actor=f"{user.role}:{user.sub}", event="plan.approved", entity=f"plan:{plan.id}",
            metadata={"comment": payload.comment or "", "case_id": case.id, "ip": client_ip(request)},
            case_id=case.id, session_id=case.session_id, fan_out=True,
            step="plan_approved", message=f"plan v{plan.version} approved by {user.sub}",
        )
        await session.commit()
        job_id = await jobs.enqueue("execute_job", plan.id)
        await write_audit(
            session, actor=f"{user.role}:{user.sub}", event="job.enqueued", entity=f"plan:{plan.id}",
            metadata={"job": "execute_job", "job_id": job_id, "ip": client_ip(request)},
            case_id=case.id, session_id=case.session_id,
        )
        await session.commit()
    else:
        if case.status not in ("awaiting_hr_approval", "executing"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot reject from status {case.status}",
            )
        case.status = "needs_attention"
        approval = ApprovalRow(plan_id=plan.id, approver_id=user.sub, decision="reject", comment=payload.comment or "")
        session.add(approval)
        await write_audit(
            session, actor=f"{user.role}:{user.sub}", event="plan.rejected", entity=f"plan:{plan.id}",
            metadata={"comment": payload.comment or "", "case_id": case.id, "ip": client_ip(request)},
            case_id=case.id, session_id=case.session_id, fan_out=True,
            step="plan_rejected", message=f"plan v{plan.version} rejected by {user.sub}",
        )
        await session.commit()

    decided = approval.decided_at or datetime.now(timezone.utc)
    return Approval(
        id=approval.id, plan_id=approval.plan_id, approver_id=approval.approver_id,
        decision=approval.decision, decided_at=decided,
    )
