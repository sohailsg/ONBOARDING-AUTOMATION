"""F-API-8 admin: reindex + 07 hardening ops (audit export, retention dry-run,
kill-switch, DLQ, readiness gate). All hr_admin only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .. import jobs
from ..audit_export import check_case_completeness, export_audit_csv
from ..auth import TokenData, require_roles
from ..config import get_settings
from ..db import get_session
from ..ratelimit import limiter

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/reindex", status_code=202)
@limiter.limit("2/hour")
async def reindex(
    request: Request,
    user: TokenData = Depends(require_roles("hr_admin")),
) -> dict:
    job_id = await jobs.enqueue("ingest_job")
    return {"status": "queued", "job_id": job_id}


@router.get("/audit/export", response_class=PlainTextResponse)
async def audit_export(
    case_id: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=20000),
    user: TokenData = Depends(require_roles("hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> PlainTextResponse:
    """7.3 read-only auditor export (CSV, PII-redacted)."""
    csv_text = await export_audit_csv(session, case_id=case_id, limit=limit)
    return PlainTextResponse(csv_text, media_type="text/csv")


@router.get("/audit/completeness/{case_id}")
async def audit_completeness(
    case_id: str,
    user: TokenData = Depends(require_roles("hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """7.3 per-action completeness check for one hire trail."""
    return await check_case_completeness(session, case_id)


@router.get("/retention/dry-run")
async def retention_dry_run(
    chat_months: int = Query(default=12, ge=1, le=120),
    trace_months: int = Query(default=6, ge=1, le=120),
    user: TokenData = Depends(require_roles("hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """7.2 legal sign-off helper: report what retention WOULD redact (no writes)."""
    from ..retention import run_retention

    res = await run_retention(
        session, chat_months=chat_months, trace_months=trace_months, dry_run=True
    )
    return res.as_dict()


@router.get("/readiness")
async def readiness(
    user: TokenData = Depends(require_roles("hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """7.7 pilot promotion gate: scans + config + queue health in one call."""
    from sqlalchemy import func, select

    from ..metrics import snapshot
    from ..models import OnboardingCase

    settings = get_settings()
    prod_problems = settings.validate_production()
    needs = (
        (await session.execute(
            select(func.count()).select_from(OnboardingCase).where(
                OnboardingCase.status == "needs_attention"
            )
        )).scalar() or 0
    )
    stale_attention = int(needs)  # age breakdown lives in the pilot report
    dlq = jobs.dlq_depth()
    metrics = snapshot()
    ready = not prod_problems and dlq == 0
    return {
        "ready": ready,
        "env": settings.ENV,
        "production_blockers": prod_problems,
        "needs_attention_open": stale_attention,
        "dlq_depth": dlq,
        "metrics": metrics,
    }


@router.post("/kill-switch/{case_id}")
async def kill_switch_halt(
    case_id: str,
    user: TokenData = Depends(require_roles("hr_admin")),
) -> dict:
    """7.5 HR kill switch: halt further tool effects for a case (audited)."""
    from ...executor import request_halt
    from .. import audit as audit_mod

    request_halt(case_id)
    try:
        from ..db import get_session_factory

        factory = get_session_factory()
        async with factory() as s:
            await audit_mod.write_audit(
                s, actor=f"{user.role}:{user.sub}", event="execute.halted",
                entity=f"case:{case_id}", metadata={"by": user.sub},
                case_id=case_id,
            )
            await s.commit()
    except Exception:
        pass
    return {"case_id": case_id, "halted": True}


@router.delete("/kill-switch/{case_id}")
async def kill_switch_clear(
    case_id: str,
    user: TokenData = Depends(require_roles("hr_admin")),
) -> dict:
    """Clear a previously requested halt (resume)."""
    from ...executor import clear_halt

    clear_halt(case_id)
    return {"case_id": case_id, "halted": False}


@router.get("/dlq")
async def dlq_list(
    user: TokenData = Depends(require_roles("hr_admin")),
) -> dict:
    """7.5 DLQ depth + entries (drain <4h SLO tracked in pilot report)."""
    return {"depth": jobs.dlq_depth(), "entries": jobs.dlq_entries()}


@router.post("/dlq/drain")
async def dlq_drain(
    user: TokenData = Depends(require_roles("hr_admin")),
) -> dict:
    drained = await jobs.drain_dlq()
    return {"drained": drained, "depth": jobs.dlq_depth()}
