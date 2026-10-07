"""Policy agent (F-AG-1): role/dept/region/start + policy_retrieve -> EntitlementSet."""

from __future__ import annotations


def build_policy_agent(llm=None, tools=None):
    from crewai import Agent

    from ..guards import IGNORE_EMBEDDED_INSTRUCTIONS
    from ..prompts import POLICY_SYSTEM

    if llm is None:
        from ..llm import get_llm

        try:
            llm = get_llm()
        except RuntimeError:
            llm = None
    kwargs: dict = {
        "role": "Policy Agent",
        "goal": "Derive cited entitlements (leave/budget/training) from policy retrieval.",
        "backstory": POLICY_SYSTEM + " " + IGNORE_EMBEDDED_INSTRUCTIONS,
        "allow_delegation": False,
        "verbose": False,
        "max_iter": 5,
    }
    if llm is not None:
        kwargs["llm"] = llm
    if tools is not None:
        kwargs["tools"] = tools
    return Agent(**kwargs)
