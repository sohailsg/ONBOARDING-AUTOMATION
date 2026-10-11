"""0002 executor execution order + statuses (05-impl follow-up).

- Adds `actions.seq` (0-based position in plan; executor replays in seq
  order instead of relying on heap/insertion order).
- Backfills seq per plan in (created_at, id) order.
- Widens `ck_actions_status` to the spec-05 words `succeeded`/`halted`
  (legacy `done`/`skipped` stay accepted so old rows keep validating).

Revision ID: 0002_executor_status_seq
Revises: 0001_initial
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_executor_status_seq"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

LEGACY_CHECK = "status IN ('pending', 'running', 'done', 'failed', 'skipped')"
WIDE_CHECK = (
    "status IN ('pending', 'running', 'succeeded', 'done', "
    "'failed', 'halted', 'skipped')"
)

BACKFILL_SEQ = """
WITH ranked AS (
  SELECT id,
         ROW_NUMBER() OVER (
           PARTITION BY plan_id ORDER BY created_at, id
         ) - 1 AS rn
  FROM actions
)
UPDATE actions SET seq = ranked.rn
FROM ranked WHERE actions.id = ranked.id
"""

# Downgrade maps executor words back to the legacy equivalents first so the
# restored narrow CHECK never rejects surviving rows.
MAP_BACK = """
UPDATE actions SET status = 'done' WHERE status = 'succeeded';
UPDATE actions SET status = 'skipped' WHERE status = 'halted';
"""


def upgrade() -> None:
    op.add_column("actions", sa.Column("seq", sa.Integer(), nullable=True))
    op.execute(sa.text(BACKFILL_SEQ))
    op.drop_constraint("ck_actions_status", "actions", type_="check")
    op.create_check_constraint("ck_actions_status", "actions", sa.text(WIDE_CHECK))


def downgrade() -> None:
    op.execute(sa.text(MAP_BACK))
    op.drop_constraint("ck_actions_status", "actions", type_="check")
    op.create_check_constraint("ck_actions_status", "actions", sa.text(LEGACY_CHECK))
    op.drop_column("actions", "seq")
