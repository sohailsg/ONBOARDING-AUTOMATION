"""4.1 schema + validator tests: invalid plans rejected, valid fixture accepted."""

from __future__ import annotations

import json
import pathlib

import pytest
from pydantic import ValidationError

from ..schemas import (
    EntitlementSet,
    FullPlanPayload,
    OnboardingPlan,
    SystemActionPlan,
    validate_full_plan,
)

FIX = pathlib.Path(__file__).parents[2] / "tests" / "fixtures"


def _good_entitlements() -> dict:
    return {"entitlements": [
        {"kind": "leave",
         "detail": "25 days annual leave + 8 bank holidays",
         "citation": {"doc": "UK-Employee-Handbook-2026.pdf", "page": 14,
                      "effective_date": "2026-04-01"}},
        {"kind": "equipment_budget",
         "detail": "GBP 500 remote home-office budget",
         "citation": {"doc": "UK-Employee-Handbook-2026.pdf", "page": 22,
                      "effective_date": "2026-04-01"}},
    ]}


def _good_plan() -> dict:
    return {"milestones": [
        {"phase": "Day1", "items": [{"title": "Complete tax forms", "due_day": 1, "mandatory": True}]},
        {"phase": "Week1", "items": [{"title": "Meet buddy + manager 1:1", "due_day": 5, "mandatory": True}]},
        {"phase": "Month1", "items": [{"title": "Own first feature", "due_day": 30, "mandatory": False}]},
    ], "meetings": [], "checklist": [
        {"title": "Complete tax forms", "due_day": 1, "mandatory": True},
    ]}


def _good_actions(prefix: str = "case:1") -> dict:
    return {"actions": [
        {"type": "send_email", "payload": {"to": "a@x.com", "subject": "s", "body": "b"},
         "idempotency_key": f"{prefix}:0"},
        {"type": "create_ticket", "payload": {"title": "t", "queue": "IT", "body": "b"},
         "idempotency_key": f"{prefix}:1"},
    ]}


def test_valid_full_plan_accepted():
    payload = {"entitlements": _good_entitlements(), "plan": _good_plan(),
               "actions": _good_actions()}
    assert validate_full_plan(payload).plan.milestones[0].phase == "Day1"


def test_entitlement_without_citation_rejected():
    bad = {"entitlements": [{"kind": "leave", "detail": "x",
                             "citation": {"doc": "", "page": 1}}]}
    with pytest.raises(ValidationError):
        EntitlementSet.model_validate(bad)


def test_bad_entitlement_kind_rejected():
    bad = {"entitlements": [{"kind": "free-money", "detail": "x",
                             "citation": {"doc": "d.pdf", "page": 1}}]}
    with pytest.raises(ValidationError):
        EntitlementSet.model_validate(bad)


def test_plan_missing_day1_rejected():
    bad = {"milestones": [
        {"phase": "Week1", "items": [{"title": "x", "due_day": 5, "mandatory": False}]}],
        "meetings": [], "checklist": []}
    with pytest.raises(ValidationError):
        OnboardingPlan.model_validate(bad)


def test_duplicate_action_keys_rejected():
    dup = {"actions": [
        {"type": "send_email", "payload": {"to": "a", "subject": "s", "body": "b"},
         "idempotency_key": "dup"},
        {"type": "send_email", "payload": {"to": "a", "subject": "s", "body": "b"},
         "idempotency_key": "dup"},
    ]}
    with pytest.raises(ValidationError):
        SystemActionPlan.model_validate(dup)


def test_wrong_action_payload_rejected():
    bad = {"actions": [{"type": "send_email", "payload": {"to": "a"},
                       "idempotency_key": "k1"}]}
    with pytest.raises(ValidationError):
        SystemActionPlan.model_validate(bad)


def test_sample_entitlements_fixture_valid():
    ent = json.loads((FIX / "sample_entitlements.json").read_text())
    assert EntitlementSet.model_validate(ent)


def test_full_payload_roundtrip_preserves_prompt_version():
    payload = {"entitlements": _good_entitlements(), "plan": _good_plan(),
               "actions": _good_actions()}
    parsed = validate_full_plan(payload)
    assert parsed.prompt_version == "v4"
    assert FullPlanPayload.model_validate(parsed.model_dump()).schema_version == "v1"
