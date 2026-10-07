"""Append-only audit writer (audit.py). Every mutation writes audit_events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditEvent
from .pii import scrub_mapping
from .sse import publish


async def write_audit(
    session: AsyncSession,
    *,
    actor: str,
    event: str,
    entity: str,
    metadata: dict[str, Any] | None = None,
    case_id: str | None = None,
    session_id: str | None = None,
    fan_out: bool = False,
    step: str | None = None,
    message: str | None = None,
) -> AuditEvent:
    row = AuditEvent(
        actor=actor,
        event=event,
        entity=entity,
        metadata_=scrub_mapping(metadata or {}),
        case_id=case_id,
        session_id=session_id,
        ts=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(row)
    await session.flush()
    # Fan-out trace events to SSE so HR UI streams live progress.
    if fan_out and session_id:
        await publish(session_id, step or event, message or event, case_id or "")
    return row
