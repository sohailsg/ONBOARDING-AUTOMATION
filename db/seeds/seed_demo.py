"""W1 (01-infra-data-impl, task 1.5). Idempotent demo seed.

Seeds 1 region (UK) + 2 hires + their cases, v1 plans, actions,
checklist items and audit trail. Re-runnable: deterministic UUIDs
(uuid5) + ON CONFLICT DO NOTHING, so row counts are stable across runs.

Usage:  python db/seeds/seed_demo.py      # from onboarding/
        make seed
Never runs in pilot — pilot data enters via Workflow A (impl §6).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import uuid

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert

_HERE = pathlib.Path(__file__).resolve()
_ONBOARDING = _HERE.parent.parent.parent  # onboarding/
if str(_ONBOARDING) not in sys.path:
    sys.path.insert(0, str(_ONBOARDING))

from db.models import (  # noqa: E402
    Action,
    AuditEvent,
    ChecklistItem,
    Employee,
    OnboardingCase,
    Plan,
)

FIXTURES = _ONBOARDING / "tests" / "fixtures"
REGION = "UK"


def _uuid(*parts: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "onboarding:" + ":".join(parts))


def _db_url() -> str:
    from db.database import get_database_url

    return get_database_url(sync=True)


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _seed_rows():
    """Build all rows with deterministic ids. Pure function (testable)."""
    hire1 = _load_fixture("sample_hire.json")
    plan_fixture = _load_fixture("sample_plan.json")

    hire2 = {
        "employee_id": str(_uuid("seed", "hire2")),
        "name": "Ravi Patel",
        "role": "Product Designer",
        "dept": "Design",
        "region": REGION,
        "manager_id": hire1["manager_id"],
        "buddy_id": hire1["buddy_id"],
        "timezone": "Europe/London",
        "start_date": "2026-11-15",
    }

    employees, cases, plans, actions, items, audits = [], [], [], [], [], []
    for hire in (hire1, hire2):
        assert hire["region"] == REGION, "seed covers exactly 1 region (UK)"
        eid = uuid.UUID(hire["employee_id"])
        start = dt.date.fromisoformat(hire["start_date"])
        employees.append(
            {
                "id": eid,
                "name": hire["name"],
                "role": hire["role"],
                "dept": hire["dept"],
                "region": hire["region"],
                "manager_id": uuid.UUID(hire["manager_id"])
                if hire.get("manager_id")
                else None,
                "buddy_id": uuid.UUID(hire["buddy_id"])
                if hire.get("buddy_id")
                else None,
                "timezone": hire.get("timezone"),
                "start_date": start,
            }
        )
        case_id = _uuid("case", str(eid))
        idem = f"{eid}:{start.isoformat()}"
        cases.append(
            {
                "id": case_id,
                "employee_id": eid,
                "status": "pending_ingestion",
                "current_plan_version": 1,
                "idempotency_key": idem,
            }
        )
        plan_id = _uuid("plan", str(case_id), "v1")
        payload = {
            "milestones": plan_fixture["milestones"],
            "hire": {
                "name": hire["name"],
                "role": hire["role"],
                "dept": hire["dept"],
                "region": hire["region"],
                "start_date": start.isoformat(),
            },
        }
        plans.append(
            {
                "id": plan_id,
                "case_id": case_id,
                "version": 1,
                "json_payload": payload,
                "created_by": "seed_demo",
            }
        )
        for i, a in enumerate(plan_fixture["actions"]):
            actions.append(
                {
                    "id": _uuid("action", str(plan_id), str(i)),
                    "plan_id": plan_id,
                    "seq": i,
                    "type": a["type"],
                    "payload": a["payload"],
                    "status": "pending",
                    "attempts": 0,
                    # Namespaced per case so the two hires don't collide on
                    # the fixture's raw idempotency keys (UNIQUE column).
                    "idempotency_key": f"{case_id}:{a['idempotency_key']}",
                }
            )
        due = 1
        for ms in plan_fixture["milestones"]:
            for entry in ms["items"]:
                items.append(
                    {
                        "id": _uuid(
                            "checklist", str(case_id), entry["title"]
                        ),
                        "case_id": case_id,
                        "title": entry["title"],
                        "due_day": entry.get("due_day", due),
                        "mandatory": bool(entry.get("mandatory", True)),
                    }
                )
            due += 1
        audits.append(
            {
                "id": _uuid("audit", str(case_id), "created"),
                "actor": "seed_demo",
                "event": "case.created",
                "entity": f"onboarding_case:{case_id}",
                "metadata": {"idempotency_key": idem, "region": REGION},
            }
        )
    return employees, cases, plans, actions, items, audits


def _upsert(engine, model, rows: list[dict]) -> int:
    """Insert-or-ignore; returns rows actually inserted."""
    if not rows:
        return 0
    stmt = pg_insert(model.__table__).values(rows)
    # Ignore conflicts on PK and on any UNIQUE column present.
    stmt = stmt.on_conflict_do_nothing()
    with engine.begin() as conn:
        result = conn.execute(stmt)
    return result.rowcount or 0


def seed() -> dict[str, int]:
    engine = create_engine(_db_url(), pool_pre_ping=True)
    employees, cases, plans, actions, items, audits = _seed_rows()
    inserted = {
        "employees": _upsert(engine, Employee, employees),
        "onboarding_cases": _upsert(engine, OnboardingCase, cases),
        "plans": _upsert(engine, Plan, plans),
        "actions": _upsert(engine, Action, actions),
        "checklist_items": _upsert(engine, ChecklistItem, items),
        "audit_events": _upsert(engine, AuditEvent, audits),
    }
    engine.dispose()
    return inserted


def main() -> None:
    inserted = seed()
    total = sum(inserted.values())
    print(f"seed_demo: inserted {total} rows " + str(inserted))


if __name__ == "__main__":
    main()
