"""Experience agent (F-AG-2): EntitlementSet + find_slots -> OnboardingPlan."""

from __future__ import annotations


def build_experience_agent(llm=None, tools=None):
    from crewai import Agent

    from ..prompts import EXPERIENCE_SYSTEM

    if llm is None:
        from ..llm import get_llm

        try:
            llm = get_llm()
        except RuntimeError:
            llm = None
    kwargs: dict = {
        "role": "Experience Agent",
        "goal": "Build Day1/Week1/Month1 milestones, meetings and checklist from entitlements + calendars.",
        "backstory": EXPERIENCE_SYSTEM,
        "allow_delegation": False,
        "verbose": False,
        "max_iter": 5,
    }
    if llm is not None:
        kwargs["llm"] = llm
    if tools is not None:
        kwargs["tools"] = tools
    return Agent(**kwargs)
