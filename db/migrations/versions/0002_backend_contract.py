"""0002 backend contract columns (02-impl integration).

Adds columns the gateway/worker read at runtime:
- onboarding_cases.session_id  (trace:{session_id} pub/sub + SSE fan-out)
- audit_events.case_id / session_id (case-scoped audit trail)

All nullable (no backfill needed); writers fill them going forward.
Spec §7 update: audit_events gains case/session scope columns.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_backend_contract"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "onboarding_cases",
        sa.Column("session_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("case_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("session_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_audit_events_case", "audit_events", ["case_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_case", table_name="audit_events")
    op.drop_column("audit_events", "session_id")
    op.drop_column("audit_events", "case_id")
    op.drop_column("onboarding_cases", "session_id")
