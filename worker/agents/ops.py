"""Ops planner (F-AG-3): OnboardingPlan -> SystemActionPlan. NO tools by design."""

from __future__ import annotations


def build_ops_agent(llm=None):
    from crewai import Agent

    from ..prompts import OPS_SYSTEM

    if llm is None:
        from ..llm import get_llm

        try:
            llm = get_llm()
        except RuntimeError:
            llm = None
    kwargs: dict = {
        "role": "Ops Planner",
        "goal": "Propose typed system actions with idempotency keys; never execute side effects.",
        "backstory": OPS_SYSTEM,
        "allow_delegation": False,
        "verbose": False,
        "max_iter": 3,
        "tools": [],  # no-tool planner: assertion target for F-AG-3 test
    }
    if llm is not None:
        kwargs["llm"] = llm
    return Agent(**kwargs)
