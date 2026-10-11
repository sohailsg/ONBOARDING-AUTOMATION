"""F-MCP-4 kill switch: HR halts remaining actions for a case (05-impl 5.4).

``POST /api/v1/execute/{case_id}/halt`` (hr_admin) sets the halt flag the
runner checks between actions; the in-flight tool call settles. Remaining
``pending`` actions flip to ``halted``, the case moves to ``needs_attention``,
and the halt is audit-logged.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:  # canonical path (executor package next to app/)
    from onboarding.backend.executor import is_halt_requested, request_halt
except ImportError:  # pragma: no cover - fallback keeps gateway importable standalone
    _HALT: set[str] = set()

    def is_halt_requested(case_id: str) -> bool:
        return case_id in _HALT

    def request_halt(case_id: str) -> None:
        _HALT.add(case_id)

from ..audit import write_audit
from ..auth import TokenData, require_roles
from ..db import get_session
from ..models import Action, Plan
from ._shared import get_case_or_404

router = APIRouter(prefix="/api/v1/execute", tags=["execute"])


@router.post("/{case_id}/halt")
async def halt_execution(
    case_id: str,
    user: TokenData = Depends(require_roles("hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    case = await get_case_or_404(session, case_id)
    already = is_halt_requested(case.id)
    request_halt(case.id)

    halted = 0
    if case.current_plan_version > 0:
        res = await session.execute(
            select(Plan).where(Plan.case_id == case.id, Plan.version == case.current_plan_version)
        )
        plan = res.scalars().first()
        if plan is not None:
            acts = (
                (await session.execute(select(Action).where(Action.plan_id == plan.id))).scalars().all()
            )
            for action in acts:
                if (action.status or "pending").strip() == "pending":
                    action.status = "halted"
                    action.last_error = "halt requested"
                    halted += 1
    if case.status == "executing":
        case.status = "needs_attention"
    await write_audit(
        session, actor=f"{user.role}:{user.sub}", event="execution.halt_requested",
        entity=f"case:{case.id}",
        metadata={"case_id": case.id, "actions_halted": halted, "already_halted": already,
                  "from_status": "executing"},
        case_id=case.id, session_id=case.session_id,
    )
    await session.commit()
    return {"case_id": case.id, "status": case.status, "actions_halted": halted, "halted": True}
