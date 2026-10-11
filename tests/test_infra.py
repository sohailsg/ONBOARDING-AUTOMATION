"""W1 infra tests (impl §5, RTM). Require live Postgres; skip otherwise.

Run:  make test-infra        # from onboarding/, DB up (make up && make migrate)
      pytest -m infra tests -q
"""
from __future__ import annotations

import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text

from db.database import get_database_url
from db.models import AuditEvent
from db.seeds.seed_demo import seed

pytestmark = pytest.mark.infra

# Snapshot at import: other suites (e.g. backend/tests/test_gateway.py) set
# DATABASE_URL at module-import (collection) time. The alembic subprocess
# below must always target the real Postgres, whatever the process env
# becomes later.
_IMPORT_TIME_DATABASE_URL = os.environ.get("DATABASE_URL")


def _engine():
    try:
        eng = create_engine(get_database_url(sync=True), pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return eng
    except Exception as exc:  # pragma: no cover — no DB in unit CI
        pytest.skip(f"no live Postgres ({exc})")


def _table_count(engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text(f"SELECT count(*) FROM {table}")
        ).scalar()


def test_schema_has_8_tables():
    eng = _engine()
    tables = set(inspect(eng).get_table_names())
    assert {
        "employees", "onboarding_cases", "plans", "approvals",
        "actions", "checklist_items", "audit_events", "chat_logs",
    } <= tables


def test_idempotency_key_unique():
    """F-IN-3: duplicate idempotency key → IntegrityError (maps to 409)."""
    from sqlalchemy.exc import IntegrityError

    eng = _engine()
    key = "infra-test-dupe:2026-11-01"
    eid = uuid.uuid5(uuid.NAMESPACE_URL, "infra-test-dupe")
    with eng.begin() as conn:
        conn.execute(
            text("DELETE FROM onboarding_cases WHERE idempotency_key=:k"),
            {"k": key},
        )
        conn.execute(
            text("DELETE FROM employees WHERE id=:e"), {"e": str(eid)}
        )
    with eng.begin() as conn:
        conn.execute(
            text("INSERT INTO employees (id,name,role,dept,region) "
                 "VALUES (:e,'T','R','D','UK')"),
            {"e": str(eid)},
        )
        conn.execute(
            text("INSERT INTO onboarding_cases "
                 "(id,employee_id,status,idempotency_key) "
                 "VALUES (gen_random_uuid(),:e,'pending_ingestion',:k)"),
            {"e": str(eid), "k": key},
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                text("INSERT INTO onboarding_cases "
                     "(id,employee_id,status,idempotency_key) "
                     "VALUES (gen_random_uuid(),:e,'pending_ingestion',:k)"),
                {"e": str(eid), "k": key},
            )


def test_audit_events_append_only():
    """Task 1.4: UPDATE/DELETE on audit_events must raise."""
    from sqlalchemy.exc import DBAPIError

    eng = _engine()
    aid = uuid.uuid5(uuid.NAMESPACE_URL, "infra-test-audit")
    with eng.begin() as conn:
        conn.execute(
            text("INSERT INTO audit_events (id,actor,event,entity,metadata) "
                 "VALUES (:a,'infra-test','test.event','case:x','{}') "
                 "ON CONFLICT (id) DO NOTHING"),
            {"a": str(aid)},
        )
    # Separate transactions: the first failure aborts its own tx.
    with eng.begin() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(
                text("UPDATE audit_events SET actor='x' WHERE id=:a"),
                {"a": str(aid)},
            )
    with eng.begin() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(
                text("DELETE FROM audit_events WHERE id=:a"),
                {"a": str(aid)},
            )


def test_seed_idempotent():
    """F-IN-4: re-running the seed keeps row counts stable."""
    eng = _engine()
    seed()
    tables = ["employees", "onboarding_cases", "plans", "actions",
              "checklist_items", "audit_events"]
    before = {t: _table_count(eng, t) for t in tables}
    inserted = seed()
    after = {t: _table_count(eng, t) for t in tables}
    assert before == after
    assert sum(inserted.values()) == 0, inserted
    assert after["employees"] >= 2 and after["onboarding_cases"] >= 2


def test_audit_model_table_name_matches_migration():
    assert AuditEvent.__tablename__ == "audit_events"


def test_migrations_render_offline_both_directions(tmp_path):
    """Downgrade path renders clean SQL (safe: never touches live data)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    if _IMPORT_TIME_DATABASE_URL:
        # Immune to collection-time env mutation by other test modules.
        env["DATABASE_URL"] = _IMPORT_TIME_DATABASE_URL
    for cmd in ("upgrade base:head --sql", "downgrade head:base --sql"):
        proc = subprocess.run(
            ["alembic", "-c", "db/alembic.ini", *cmd.split()],
            cwd=root, capture_output=True, text=True, timeout=60, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert "CREATE TABLE" in proc.stdout or "DROP TABLE" in proc.stdout
