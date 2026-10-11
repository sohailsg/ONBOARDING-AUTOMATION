"""Pydantic v2 request/response models mirroring 01 tables + openapi.yaml."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class CaseStatus(str, Enum):
    PENDING_INGESTION = "pending_ingestion"
    AGENT_PROCESSING = "agent_processing"
    AWAITING_HR_APPROVAL = "awaiting_hr_approval"
    EXECUTING = "executing"
    NEEDS_ATTENTION = "needs_attention"
    ACTIVE = "active"


class HireRecord(BaseModel):
    name: str = Field(min_length=1)
    role: str = ""
    dept: str = ""
    region: str = ""
    timezone: str = ""
    manager_id: str | None = None
    buddy_id: str | None = None
    start_date: str = Field(min_length=1)  # YYYY-MM-DD, validated lightly (01 owns canonical types)


class Case(BaseModel):
    id: str
    employee_id: str
    status: CaseStatus
    current_plan_version: int
    idempotency_key: str
    # Nullable: rows created before migration 0002 (backend contract) carry
    # no session_id; the column is nullable in DDL too.
    session_id: str | None = None


class CasePage(BaseModel):
    items: list[Case]
    page: int
    page_size: int
    total: int


class ActionPayload(BaseModel):
    type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class PlanIn(BaseModel):
    json_payload: dict[str, Any] = Field(default_factory=dict)
    actions: list[ActionPayload] = Field(default_factory=list)


class Plan(BaseModel):
    id: str
    case_id: str
    version: int
    json_payload: dict[str, Any]
    created_by: str
    actions: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str = ""


class Approval(BaseModel):
    id: str
    plan_id: str
    approver_id: str
    decision: str
    decided_at: datetime


class ChecklistPatch(BaseModel):
    completed: bool


class ChecklistItem(BaseModel):
    id: str
    title: str
    due_day: int
    mandatory: bool
    completed_at: datetime | None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class Citation(BaseModel):
    doc: str
    page: int | None = None
    effective_date: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    confidence: float


class TraceEvent(BaseModel):
    ts: datetime
    step: str
    message: str
    case_id: str
    session_id: str
    id: int | None = None


# Back-compat aliases while routers finish the rename to Case/Plan/
# ChecklistItem/Approval (W2 in flight): identical shapes.
CaseOut = Case
PlanOut = Plan
ChecklistItemOut = ChecklistItem
ApprovalOut = Approval
