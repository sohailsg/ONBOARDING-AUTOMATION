"""Dev-only login bridge (02-impl SSO stub, T-1).

The Next.js login page collects only a *role*; the API needs a credential
whose ``sub`` resolves to a real row (employees own their cases). In
production this endpoint MUST NOT exist — OIDC mints the JWT and the
middleware holds it httpOnly. Here, with JWT_DEV_STUB=true, it mints the
same ``dev:<role>:<sub>`` tokens tests use and binds employee logins to a
real employee row (explicit id wins, else the most recently created hire).

Disabled (404) whenever JWT_DEV_STUB is false so no stub credential path
can survive into staging/pilot/prod.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import TokenData, get_current_user, mint_dev_token
from ..config import get_settings
from ..db import get_session
from ..models import Employee, OnboardingCase

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class DevLoginIn(BaseModel):
    role: Literal["employee", "hr_admin"]
    employee_id: str | None = None


class DevLoginOut(BaseModel):
    token: str
    role: str
    sub: str


@router.post("/dev-login", response_model=DevLoginOut)
async def dev_login(
    payload: DevLoginIn,
    session: AsyncSession = Depends(get_session),
    settings=Depends(get_settings),
) -> DevLoginOut:
    if not settings.JWT_DEV_STUB:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="dev login disabled")
    if payload.role == "hr_admin":
        sub = "hr-1"
    elif payload.employee_id:
        employee = await session.get(Employee, payload.employee_id)
        if employee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="employee profile not found")
        sub = employee.id
    else:
        # Latest hire's employee (cases carry created_at; employees don't).
        res = await session.execute(
            select(OnboardingCase).order_by(OnboardingCase.created_at.desc()).limit(1))
        case = res.scalars().first()
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="no employees yet — trigger a hire first")
        sub = case.employee_id
    return DevLoginOut(token=mint_dev_token(payload.role, sub),
                       role=payload.role, sub=sub)


@router.get("/whoami", response_model=DevLoginOut)
async def whoami(user: TokenData = Depends(get_current_user)) -> DevLoginOut:
    """Resolved identity for the bearer (token echoed empty); drives role routing."""
    return DevLoginOut(token="", role=user.role, sub=user.sub)
