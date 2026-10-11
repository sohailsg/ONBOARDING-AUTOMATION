"""F-API-1 trigger: idempotent intake (role `service`, Idempotency-Key required)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import jobs
from ..audit import write_audit
from ..auth import TokenData, require_roles
from ..db import get_session
from ..models import Employee, OnboardingCase
from ..ratelimit import limiter
from ..schemas import Case, HireRecord
from ._shared import case_out, client_ip

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


def _parse_date(value: str) -> date | None:
    try:
        y, m, d = (int(p) for p in value.split("-"))
        return date(y, m, d)
    except Exception:
        return None


@router.post("/trigger", response_model=Case, status_code=201)
@limiter.limit("60/minute")
async def trigger_onboarding(
    request: Request,
    payload: HireRecord,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: TokenData = Depends(require_roles("service")),
    session: AsyncSession = Depends(get_session),
) -> Case:
    if not idempotency_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key header required")
    if len(idempotency_key) > 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key max 128 chars")

    # Duplicate key -> 200 existing case (F-API-1 / F-IN-3).
    existing = await session.execute(
        select(OnboardingCase).where(OnboardingCase.idempotency_key == idempotency_key)
    )
    row = existing.scalars().first()
    if row is not None:
        response.status_code = status.HTTP_200_OK
        return case_out(row)

    employee = Employee(
        name=payload.name, role=payload.role, dept=payload.dept, region=payload.region,
        timezone=payload.timezone or "", manager_id=payload.manager_id, buddy_id=payload.buddy_id,
        start_date=_parse_date(payload.start_date),
    )
    session.add(employee)
    await session.flush()
    case = OnboardingCase(
        employee_id=employee.id, status="pending_ingestion",
        current_plan_version=0, idempotency_key=idempotency_key,
    )
    session.add(case)
    try:
        await session.flush()
    except IntegrityError:
        # Lost a race with a concurrent duplicate insert -> return existing.
        await session.rollback()
        dup = await session.execute(
            select(OnboardingCase).where(OnboardingCase.idempotency_key == idempotency_key)
        )
        found = dup.scalars().first()
        if found is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency conflict")
        response.status_code = status.HTTP_200_OK
        return case_out(found)

    await write_audit(
        session, actor=f"service:{user.sub}", event="case.triggered", entity=f"case:{case.id}",
        metadata={"idempotency_key": idempotency_key, "employee_id": employee.id, "ip": client_ip(request)},
        case_id=case.id, session_id=case.session_id,
    )
    await session.commit()
    job_id = await jobs.enqueue("plan_job", case.id, case.session_id)
    await write_audit(
        session, actor=f"service:{user.sub}", event="job.enqueued", entity=f"case:{case.id}",
        metadata={"job": "plan_job", "job_id": job_id, "ip": client_ip(request)},
        case_id=case.id, session_id=case.session_id,
    )
    await session.commit()
    response.status_code = status.HTTP_201_CREATED
    return case_out(case)
