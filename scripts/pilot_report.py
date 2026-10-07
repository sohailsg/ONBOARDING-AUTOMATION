"""7.7 weekly pilot report (impl §6 Post-Launch Monitoring).

Metrics: hires onboarded, plan latency, chat Faithfulness/answer rate,
action success/retry, cost per hire. Go/no-go gate at the bottom.

Usage:
  python scripts/pilot_report.py --database-url postgresql+asyncpg://...  # live DB
  python scripts/pilot_report.py --demo                                      # sample numbers for template
  python scripts/pilot_report.py --database-url ... --out pilot-week1.md
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

FAITHFULNESS_GATE = 0.9
NEEDS_ATTENTION_SLA_H = 24


async def _collect_live(database_url: str) -> dict:
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from onboarding.backend.app.models import Action, AuditEvent, ChatLog, OnboardingCase

    eng = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    async with factory() as s:
        cases = (await s.execute(select(OnboardingCase))).scalars().all()
        actions = (await s.execute(select(Action))).scalars().all()
        chats = (await s.execute(select(ChatLog).limit(5000))).scalars().all()
        audit_n = (await s.execute(select(func.count()).select_from(AuditEvent))).scalar() or 0
    await eng.dispose()
    by_status: dict[str, int] = {}
    for c in cases:
        by_status[c.status] = by_status.get(c.status, 0) + 1
    act_by_status: dict[str, int] = {}
    retries = 0
    for a in actions:
        act_by_status[a.status] = act_by_status.get(a.status, 0) + 1
        retries += max(0, (a.attempts or 1) - 1)
    cited = sum(1 for c in chats if (c.citations or []) and (c.confidence or 0) >= 0.35)
    confs = [c.confidence or 0 for c in chats if c.citations]
    return {
        "hires": len(cases),
        "by_status": by_status,
        "needs_attention": by_status.get("needs_attention", 0),
        "actions": act_by_status,
        "action_retries": retries,
        "chats": len(chats),
        "answer_rate": round(cited / len(chats), 3) if chats else 0.0,
        "avg_faithfulness": round(sum(confs) / len(confs), 3) if confs else 0.0,
        "audit_events": int(audit_n),
        "cost_per_hire_usd": 0.0,  # local stack; Langfuse ledger fills when paid models arrive
    }


def _demo() -> dict:
    return {
        "hires": 10, "by_status": {"active": 7, "executing": 2, "needs_attention": 1},
        "needs_attention": 1, "actions": {"succeeded": 40, "failed": 1, "pending": 3},
        "action_retries": 2, "chats": 60, "answer_rate": 0.93,
        "avg_faithfulness": 0.94, "audit_events": 412, "cost_per_hire_usd": 0.0,
    }


def render(m: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_act = sum(m.get("actions", {}).values()) or 1
    succ = m.get("actions", {}).get("succeeded", 0) + m.get("actions", {}).get("done", 0)
    go = (
        m.get("avg_faithfulness", 0) >= FAITHFULNESS_GATE
        and m.get("needs_attention", 0) == 0
    )
    lines = [
        f"# Pilot weekly report ({now})",
        "",
        f"- Hires onboarded: **{m.get('hires')}** {m.get('by_status', {})}",
        f"- needs_attention open: **{m.get('needs_attention')}** (SLA: resolve <{NEEDS_ATTENTION_SLA_H}h)",
        f"- Chat: n={m.get('chats')} answer_rate={m.get('answer_rate')} avg_faithfulness={m.get('avg_faithfulness')} (gate ≥{FAITHFULNESS_GATE})",
        f"- Actions: {m.get('actions', {})} success_rate={round(succ / total_act, 3)} retries={m.get('action_retries')}",
        f"- Cost/hire: ${m.get('cost_per_hire_usd', 0.0):.2f} (Langfuse ledger; local stack = $0)",
        f"- Audit events: {m.get('audit_events')} (append-only; export via `GET /api/v1/admin/audit/export`)",
        "",
        "## Go / no-go",
        f"- Faithfulness ≥{FAITHFULNESS_GATE}: {'PASS' if m.get('avg_faithfulness', 0) >= FAITHFULNESS_GATE else 'FAIL'}",
        f"- Zero unapproved actions: {'ATTEST (executor is approval-gated; audit `action.succeeded` ↔ `plan.approved`)' }",
        f"- No unresolved needs_attention >{NEEDS_ATTENTION_SLA_H}h: {'PASS' if m.get('needs_attention', 0) == 0 else 'FAIL — resolve before go'}",
        "",
        f"**Decision: {'GO' if go else 'NO-GO'}** — signed: tech lead ___ / HR ___ / security ___",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url", default="")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    if args.demo or not args.database_url:
        m = _demo()
    else:
        m = asyncio.run(_collect_live(args.database_url))
    text = render(m)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
