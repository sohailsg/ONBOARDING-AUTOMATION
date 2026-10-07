"""W0 fixture validation — ensures mock contracts stay loadable for MSW + tests."""
from __future__ import annotations

import json
import pathlib

FIX = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIX / name).read_text())


def test_sample_hire_shape():
    hire = _load("sample_hire.json")
    for key in ("name", "role", "dept", "region", "start_date"):
        assert hire[key], key


def test_sample_entitlements_cited():
    ent = _load("sample_entitlements.json")
    assert ent["entitlements"], "need at least one entitlement"
    for item in ent["entitlements"]:
        c = item["citation"]
        assert c["doc"] and c["page"] and c["effective_date"]


def test_sample_plan_actions_idempotent():
    plan = _load("sample_plan.json")
    keys = [a["idempotency_key"] for a in plan["actions"]]
    assert len(keys) == len(set(keys)), "action idempotency keys must be unique"
    assert plan["version"] == 1


def test_trace_events_ordered():
    events = _load("trace_events.json")
    assert [e["step"] for e in events] == [
        "policy_retrieve",
        "policy_retrieve",
        "experience_plan",
        "ops_planner",
    ]


def test_chat_sample_cited():
    chat = _load("chat_sample.json")
    assert chat["citations"], "chat answer must carry citations"
    assert 0.0 <= chat["confidence"] <= 1.0
