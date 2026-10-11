"""0004 approvals decision words (02-impl integration).

The gateway contract (ApprovalDecision) records `approve`/`reject`;
the 0001 check only allowed `approved`/`rejected`/`changes_requested`.
Widen additively — old rows keep validating.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_approval_words"
down_revision = "0003_merge"
branch_labels = None
depends_on = None

NARROW = "decision IN ('approved', 'rejected', 'changes_requested')"
WIDE = (
    "decision IN ('approved', 'approve', 'rejected', 'reject', "
    "'changes_requested')"
)


def upgrade() -> None:
    op.drop_constraint("ck_approvals_decision", "approvals", type_="check")
    op.create_check_constraint("ck_approvals_decision", "approvals", sa.text(WIDE))


def downgrade() -> None:
    op.execute(sa.text("UPDATE approvals SET decision='approved' WHERE decision='approve'"))
    op.execute(sa.text("UPDATE approvals SET decision='rejected' WHERE decision='reject'"))
    op.drop_constraint("ck_approvals_decision", "approvals", type_="check")
    op.create_check_constraint("ck_approvals_decision", "approvals", sa.text(NARROW))
