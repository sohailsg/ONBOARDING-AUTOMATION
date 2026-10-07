"""7.2 retention + redaction jobs (spec F-HD-2).

Policy (strictest default, legal confirms N):
- chat_logs older than CHAT_RETENTION_MONTHS (12) -> PII-redact Q/A in place
  (row kept for answer-rate stats, content replaced with [REDACTED]).
- audit trace payloads older than TRACE_RETENTION_MONTHS (6) -> scrub metadata
  PII in place. audit_events rows are NEVER deleted (append-only, 7.3).

Runs in dry-run by default (RETENTION_DRY_RUN=true): reports candidate counts
without writing. Live run only after legal sign-off + `make retention-live`.
Works on Postgres (production) and SQLite (tests/dev) via portable SQL.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .pii import REDACTED, scrub_text

CHAT_RETENTION_MONTHS_DEFAULT = 12
TRACE_RETENTION_MONTHS_DEFAULT = 6


def cutoff(months: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return now - timedelta(days=30 * months)


@dataclass
class RetentionResult:
    chat_candidates: int = 0
    chat_redacted: int = 0
    trace_candidates: int = 0
    trace_scrubbed: int = 0
    dry_run: bool = True

    def as_dict(self) -> dict:
        return {
            "chat_candidates": self.chat_candidates,
            "chat_redacted": self.chat_redacted,
            "trace_candidates": self.trace_candidates,
            "trace_scrubbed": self.trace_scrubbed,
            "dry_run": self.dry_run,
        }


async def run_retention(
    session: AsyncSession,
    *,
    chat_months: int = CHAT_RETENTION_MONTHS_DEFAULT,
    trace_months: int = TRACE_RETENTION_MONTHS_DEFAULT,
    dry_run: bool = True,
    now: datetime | None = None,
    limit: int = 1000,
) -> RetentionResult:
    from .models import AuditEvent, ChatLog

    res = RetentionResult(dry_run=dry_run)
    chat_cut = cutoff(chat_months, now)
    trace_cut = cutoff(trace_months, now)

    chat_rows = (
        (await session.execute(
            select(ChatLog).where(ChatLog.created_at < chat_cut).limit(limit)
        )).scalars().all()
    )
    res.chat_candidates = len(chat_rows)
    trace_rows = (
        (await session.execute(
            select(AuditEvent).where(AuditEvent.ts < trace_cut).limit(limit)
        )).scalars().all()
    )
    res.trace_candidates = len(trace_rows)

    if dry_run:
        return res

    for row in chat_rows:
        row.question = REDACTED
        row.answer = REDACTED
        res.chat_redacted += 1
    for row in trace_rows:
        meta = dict(row.metadata_ or {})
        scrubbed = _scrub_metadata(meta)
        if scrubbed != meta:
            row.metadata_ = scrubbed
        res.trace_scrubbed += 1
    await session.commit()
    return res


def _scrub_metadata(meta: dict) -> dict:
    from .pii import scrub_mapping

    return scrub_mapping(meta)


async def _amain(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PII retention dry-run/live job")
    ap.add_argument("--chat-months", type=int, default=CHAT_RETENTION_MONTHS_DEFAULT)
    ap.add_argument("--trace-months", type=int, default=TRACE_RETENTION_MONTHS_DEFAULT)
    ap.add_argument("--live", action="store_true", help="write changes (default is dry-run)")
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args(argv)

    from .config import get_settings
    from .db import get_session_factory

    settings = get_settings()
    dry = not args.live
    if not dry and settings.RETENTION_DRY_RUN:
        print("refusing live run: RETENTION_DRY_RUN=true (legal sign-off flips it)")
        return 2
    factory = get_session_factory()
    async with factory() as session:
        res = await run_retention(
            session, chat_months=args.chat_months, trace_months=args.trace_months,
            dry_run=dry, limit=args.limit,
        )
    print(res.as_dict())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(__import__("asyncio").run(_amain()))
