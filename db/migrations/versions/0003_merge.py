"""0003 merge 0002 branches (backend contract + executor seq).

Revision ID: 0003_merge
Revises: 0002_backend_contract, 0002_executor_status_seq
"""
from __future__ import annotations

revision = "0003_merge"
down_revision = ("0002_backend_contract", "0002_executor_status_seq")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
