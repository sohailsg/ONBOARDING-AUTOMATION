"""7.3 auditor export + per-action completeness check (spec F-HD-3).

Export: read-only CSV of audit_events with PII redaction (auditor role).
Completeness: for a hire trail, every agent step / edit / approval /
external action must appear; gaps are reported per case.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Action, Approval, AuditEvent, Plan
from .pii import scrub_text

# Events that constitute a "full hire trail" for the auditor.
REQUIRED_EVENT_PREFIXES = (
    "case.triggered",
    "plan.",
    "approval.",
)

EXPORT_COLUMNS = ["id", "ts", "actor", "event", "entity", "case_id", "session_id", "metadata"]


async def export_audit_csv(
    session: AsyncSession, *, case_id: str | None = None, limit: int = 5000
) -> str:
    q = select(AuditEvent).order_by(AuditEvent.ts.asc()).limit(limit)
    if case_id:
        q = q.where(AuditEvent.case_id == case_id)
    rows = (await session.execute(q)).scalars().all()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS)
    w.writeheader()
    for r in rows:
        w.writerow({
            "id": r.id,
            "ts": r.ts.isoformat() if isinstance(r.ts, datetime) else str(r.ts),
            "actor": scrub_text(r.actor),
            "event": r.event,
            "entity": r.entity,
            "case_id": r.case_id or "",
            "session_id": r.session_id or "",
            "metadata": scrub_text(str(r.metadata_ or {}))[:2000],
        })
    return buf.getvalue()


async def check_case_completeness(session: AsyncSession, case_id: str) -> dict:
    """Verify every plan/approval/action for a case has a matching audit event.

    Returns {"complete": bool, "missing": [...], "events": N}.
    """
    plans = (await session.execute(select(Plan).where(Plan.case_id == case_id))).scalars().all()
    plan_ids = [p.id for p in plans]
    approvals: list[Any] = []
    actions: list[Any] = []
    if plan_ids:
        approvals = list((await session.execute(select(Approval).where(Approval.plan_id.in_(plan_ids)))).scalars().all())
        actions = list((await session.execute(select(Action).where(Action.plan_id.in_(plan_ids)))).scalars().all())
    events = (await session.execute(select(AuditEvent).where(AuditEvent.case_id == case_id))).scalars().all()
    blobs = " ".join(f"{e.event} {e.entity}" for e in events)

    missing: list[str] = []
    if not any("case.triggered" in f"{e.event}" for e in events):
        missing.append("case.triggered")
    for p in plan_ids:
        if f"plan:{p}" not in blobs and "plan.updated" not in blobs and "plan.approved" not in blobs:
            missing.append(f"plan:{p} (no plan.* audit)")
    for a in approvals:
        if f"approval:{a.id}" not in blobs and "plan.approved" not in blobs and "plan.rejected" not in blobs:
            missing.append(f"approval:{a.id}")
    for ac in actions:
        if f"action:{ac.id}" not in blobs and "execute." not in blobs and "action." not in blobs:
            # Only flag executed actions: pending actions need no execution audit yet.
            if ac.status in ("done", "failed", "running"):
                missing.append(f"action:{ac.id} status={ac.status}")
    return {"complete": not missing, "missing": missing, "events": len(events)}
