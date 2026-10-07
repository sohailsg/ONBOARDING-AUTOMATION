"""Worker package (04-agent-worker-impl). Background plan crew.

Free-stack binding: Ollama chat via OLLAMA_CHAT_MODEL, no Anthropic key.
Read-only tools only — no write-capable tool import is allowed here
(enforced by CI grep test).
"""

from .schemas import (
    PRE_APPROVAL_STATUSES,
    Action,
    ChecklistEntry,
    Citation,
    Entitlement,
    EntitlementSet,
    FullPlanPayload,
    HireContext,
    Milestone,
    MilestoneItem,
    OnboardingPlan,
    Slot,
    SystemActionPlan,
    TraceEvent,
    validate_full_plan,
)

__all__ = [
    "PRE_APPROVAL_STATUSES",
    "Action",
    "ChecklistEntry",
    "Citation",
    "Entitlement",
    "EntitlementSet",
    "FullPlanPayload",
    "HireContext",
    "Milestone",
    "MilestoneItem",
    "OnboardingPlan",
    "Slot",
    "SystemActionPlan",
    "TraceEvent",
    "validate_full_plan",
]
