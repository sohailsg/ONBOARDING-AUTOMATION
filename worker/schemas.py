"""4.1 Schemas (worker/schemas.py). Pydantic v2, versioned with prompts.

Mirrors impl §2 + spec §7 data dictionary:
  Entitlement{kind, detail, citation{doc,page,effective_date}}
  Milestone{phase: Day1|Week1|Month1, items[{title,due_day,mandatory}]}
  Action{type, payload (discriminated by type), idempotency_key}

plans.json_payload = {entitlements: EntitlementSet,
                      plan: OnboardingPlan,
                      actions: SystemActionPlan}
Prompt/schema version linkage: PROMPT_VERSION recorded on every plan.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PROMPT_VERSION = "v1"
SCHEMA_VERSION = "v1"

Phase = Literal["Day 1", "Day1", "Week 1", "Week1", "Month 1", "Month1"]
CANONICAL_PHASES = ("Day1", "Week1", "Month1")

ACTION_TYPES = (
    "send_email",
    "create_notion_page",
    "create_invite",
    "create_ticket",
    "send_slack",
)

# Statuses plan_job is allowed to start from (re-runs / dedupe safe).
PRE_APPROVAL_STATUSES = ("pending_ingestion", "agent_processing", "needs_attention")


class Citation(BaseModel):
    doc: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    effective_date: str | None = None

    @field_validator("doc")
    @classmethod
    def _doc_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("citation.doc must be non-empty")
        return v.strip()


class Entitlement(BaseModel):
    kind: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    citation: Citation

    @field_validator("kind")
    @classmethod
    def _kind_allowed(cls, v: str) -> str:
        allowed = {"leave", "equipment_budget", "mandatory_training", "benefits", "policy", "other"}
        if v not in allowed:
            raise ValueError(f"entitlement.kind must be one of {sorted(allowed)}")
        return v


class EntitlementSet(BaseModel):
    entitlements: list[Entitlement] = Field(min_length=1)

    @model_validator(mode="after")
    def _citations_present(self) -> EntitlementSet:
        for e in self.entitlements:
            if not e.citation.doc:
                raise ValueError("every entitlement must carry a citation.doc")
        return self


class MilestoneItem(BaseModel):
    title: str = Field(min_length=1)
    due_day: int = Field(ge=1, le=90)
    mandatory: bool = False


class Milestone(BaseModel):
    phase: str
    items: list[MilestoneItem] = Field(min_length=1)

    @field_validator("phase")
    @classmethod
    def _phase_canonical(cls, v: str) -> str:
        norm = v.replace(" ", "")
        if norm not in CANONICAL_PHASES:
            raise ValueError(f"phase must be one of {CANONICAL_PHASES}")
        return norm


class OnboardingPlan(BaseModel):
    milestones: list[Milestone] = Field(min_length=1)
    meetings: list[dict[str, Any]] = Field(default_factory=list)
    checklist: list[MilestoneItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _phases_cover_day1(self) -> OnboardingPlan:
        phases = {m.phase for m in self.milestones}
        if "Day1" not in phases:
            raise ValueError("plan must include a Day1 milestone")
        return self


class Action(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1)

    @field_validator("type")
    @classmethod
    def _type_allowed(cls, v: str) -> str:
        if v not in ACTION_TYPES:
            raise ValueError(f"action.type must be one of {ACTION_TYPES}")
        return v

    @model_validator(mode="after")
    def _payload_by_type(self) -> Action:
        required: dict[str, tuple[str, ...]] = {
            "send_email": ("to", "subject", "body"),
            "create_notion_page": ("owner", "template"),
            "create_invite": ("attendees", "start", "end"),
            "create_ticket": ("title", "queue", "body"),
            "send_slack": ("channel", "text"),
        }
        need = required.get(self.type, ())
        missing = [k for k in need if k not in self.payload]
        if missing:
            raise ValueError(f"action {self.type} payload missing keys: {missing}")
        return self


class SystemActionPlan(BaseModel):
    actions: list[Action] = Field(min_length=1)

    @model_validator(mode="after")
    def _keys_unique(self) -> SystemActionPlan:
        keys = [a.idempotency_key for a in self.actions]
        if len(keys) != len(set(keys)):
            raise ValueError("action idempotency keys must be unique")
        return self


class FullPlanPayload(BaseModel):
    """Exact shape stored in plans.json_payload."""

    entitlements: EntitlementSet
    plan: OnboardingPlan
    actions: SystemActionPlan
    prompt_version: str = PROMPT_VERSION
    schema_version: str = SCHEMA_VERSION


class ChecklistEntry(BaseModel):
    title: str = Field(min_length=1)
    due_day: int = Field(ge=1, le=90)
    mandatory: bool = False


class HireContext(BaseModel):
    name: str = Field(min_length=1)
    role: str = ""
    dept: str = ""
    region: str = ""
    timezone: str = ""
    manager_id: str | None = None
    buddy_id: str | None = None
    start_date: str = Field(min_length=1)
    case_id: str = ""
    session_id: str = ""


class Slot(BaseModel):
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    attendees: list[str] = Field(default_factory=list)
    status: Literal["confirmed", "tbd"] = "confirmed"


class TraceEvent(BaseModel):
    ts: str = Field(min_length=1)
    step: str = Field(min_length=1)
    message: str = Field(min_length=1)
    case_id: str = ""
    session_id: str = ""


def validate_full_plan(payload: dict[str, Any]) -> FullPlanPayload:
    """Parse + validate a candidate plan dict. Raises ValidationError if bad."""
    return FullPlanPayload.model_validate(payload)
