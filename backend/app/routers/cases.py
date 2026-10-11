"""F-API-2 pipeline list + F-API-3 SSE stream with last-N replay."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import TokenData, require_roles
from ..db import get_session
from ..models import AuditEvent, OnboardingCase
from ..schemas import CasePage, CaseStatus
from ..sse import redis_listener, subscribe_queue
from ._shared import case_out, get_case_or_404

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])

HEARTBEAT_SECONDS = 15


@router.get("", response_model=CasePage)
async def list_cases(
    status: CaseStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: TokenData = Depends(require_roles("hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> CasePage:
    q = select(OnboardingCase)
    count_q = select(func.count()).select_from(OnboardingCase)
    if status:
        q = q.where(OnboardingCase.status == status)
        count_q = count_q.where(OnboardingCase.status == status)
    total = (await session.execute(count_q)).scalar() or 0
    rows = (
        (await session.execute(q.order_by(OnboardingCase.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
        .scalars()
        .all()
    )
    return CasePage(items=[case_out(r) for r in rows], page=page, page_size=page_size, total=int(total))


def _sse_format(event: dict) -> str:
    eid = event.get("id", "")
    payload = json.dumps(event, default=str)
    prefix = f"id: {eid}\n" if eid else ""
    return f"{prefix}event: trace\ndata: {payload}\n\n"


@router.get("/{case_id}/stream")
async def stream_trace(
    request: Request,
    case_id: str,
    last_n: int = Query(default=20, ge=0, le=200),
    last_event_id: int | None = Query(default=None),
    user: TokenData = Depends(require_roles("hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    case = await get_case_or_404(session, case_id)

    # Replay last-N from audit_events on reconnect (F-API-3).
    replay_q = select(AuditEvent).where(AuditEvent.session_id == case.session_id)
    if last_event_id:
        replay_q = replay_q.where(AuditEvent.id > last_event_id)
    replay_q = replay_q.order_by(AuditEvent.ts.desc()).limit(last_n)
    replay_rows = list(reversed((await session.execute(replay_q)).scalars().all()))
    replay = [
        {
            "id": r.id, "ts": r.ts.isoformat() if isinstance(r.ts, datetime) else str(r.ts),
            "step": r.event, "message": str((r.metadata_ or {}).get("message", r.event)),
            "case_id": r.case_id or case.id, "session_id": r.session_id or case.session_id,
        }
        for r in replay_rows
    ]

    async def _gen():
        for ev in replay:
            if await request.is_disconnected():
                return
            yield _sse_format(ev)
        # NOTE: wait_for wraps queue.get(), never agen.__anext__() — the
        # latter corrupts the generator when the client disconnects.
        queue, unsub = subscribe_queue(case.session_id)
        bridge = asyncio.create_task(redis_listener(case.session_id, queue))
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield _sse_format(ev)
        finally:
            unsub()
            bridge.cancel()

    return StreamingResponse(_gen(), media_type="text/event-stream")
