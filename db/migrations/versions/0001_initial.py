"""0001 initial schema: 8 tables + checks + indexes + audit append-only.

Revision ID: 0001_initial
Revises: None
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("dept", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=False),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("buddy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "onboarding_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "employee_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("status", sa.Text(), server_default="pending_ingestion",
                   nullable=False),
        sa.Column("current_plan_version", sa.Integer(), server_default="1",
                   nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending_ingestion', 'agent_processing', "
            "'awaiting_hr_approval', 'executing', 'needs_attention', "
            "'active')",
            name="ck_onboarding_cases_status",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_onboarding_cases_status", "onboarding_cases", ["status"]
    )

    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("json_payload", postgresql.JSONB(astext_type=sa.Text()),
                   server_default="{}", nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["onboarding_cases.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_id", "version", name="uq_plans_case_version"
        ),
    )
    op.create_index("ix_plans_case_version", "plans", ["case_id", "version"])

    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected', 'changes_requested')",
            name="ck_approvals_decision",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()),
                   server_default="{}", nullable=False),
        sa.Column("status", sa.Text(), server_default="pending",
                   nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0",
                   nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed', 'skipped')",
            name="ck_actions_status",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_actions_plan_status", "actions", ["plan_id", "status"]
    )

    op.create_table(
        "checklist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("mandatory", sa.Boolean(), server_default="true",
                   nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["onboarding_cases.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()),
                   server_default="{}", nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_ts", "audit_events", ["ts"])

    op.create_table(
        "chat_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True),
                   nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()),
                   server_default="[]", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_logs_employee", "chat_logs", ["employee_id"]
    )

    # --- 1.4 audit append-only: trigger blocks UPDATE/DELETE for every
    # role (REVOKE alone does not stop owners/superusers). ---
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION audit_events_no_modify()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'audit_events is append-only';
              RETURN NULL;
            END $$;
            DROP TRIGGER IF EXISTS trg_audit_events_no_modify ON audit_events;
            CREATE TRIGGER trg_audit_events_no_modify
              BEFORE UPDATE OR DELETE ON audit_events
              FOR EACH ROW EXECUTE FUNCTION audit_events_no_modify();
            """
        )
    )
    # Belt-and-braces REVOKEs; guarded so fresh dev DBs without the
    # least-privilege roles still migrate cleanly (roles.sql creates them).
    op.execute(
        sa.text(
            """
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
                REVOKE UPDATE, DELETE ON audit_events FROM app_rw;
              END IF;
              REVOKE UPDATE, DELETE ON audit_events FROM PUBLIC;
            END $$;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_audit_events_no_modify "
            "ON audit_events"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS audit_events_no_modify()"))
    op.drop_index("ix_chat_logs_employee", table_name="chat_logs")
    op.drop_table("chat_logs")
    op.drop_index("ix_audit_events_ts", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("checklist_items")
    op.drop_index("ix_actions_plan_status", table_name="actions")
    op.drop_table("actions")
    op.drop_table("approvals")
    op.drop_index("ix_plans_case_version", table_name="plans")
    op.drop_table("plans")
    op.drop_index("ix_onboarding_cases_status",
                   table_name="onboarding_cases")
    op.drop_table("onboarding_cases")
    op.drop_table("employees")
