"""SQLAlchemy models mirroring 01 tables (01 owns DDL; gateway owns status machine)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# Status enum values (validated in schemas + transition guards).
CASE_STATUSES = (
    "pending_ingestion",
    "agent_processing",
    "awaiting_hr_approval",
    "executing",
    "needs_attention",
    "active",
)

# Allowed forward transitions (gateway-owned state machine).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending_ingestion": {"agent_processing"},
    "agent_processing": {"awaiting_hr_approval", "needs_attention"},
    "awaiting_hr_approval": {"executing", "needs_attention"},
    "executing": {"active", "needs_attention"},
    "needs_attention": {"agent_processing", "awaiting_hr_approval", "executing"},
    "active": set(),
}


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200), default="")
    dept: Mapped[str] = mapped_column(String(200), default="")
    region: Mapped[str] = mapped_column(String(100), default="")
    timezone: Mapped[str] = mapped_column(String(100), default="")
    manager_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    buddy_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class OnboardingCase(Base):
    __tablename__ = "onboarding_cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    employee_id: Mapped[str] = mapped_column(String(36), ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(40), default="pending_ingestion", index=True)
    current_plan_version: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    session_id: Mapped[str] = mapped_column(String(36), default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("case_id", "version", name="uq_plans_case_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("onboarding_cases.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    json_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(20), default="agent")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"))
    approver_id: Mapped[str] = mapped_column(String(200))
    decision: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Action(Base):
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), index=True)
    type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    external_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("onboarding_cases.id"))
    title: Mapped[str] = mapped_column(String(300))
    due_day: Mapped[int] = mapped_column(Integer, default=1)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(200))
    event: Mapped[str] = mapped_column(String(200))
    entity: Mapped[str] = mapped_column(String(200))
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ChatLog(Base):
    __tablename__ = "chat_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    employee_id: Mapped[str] = mapped_column(String(36), ForeignKey("employees.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0)  # stored 0..1 (float-tolerant column)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
