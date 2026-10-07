"""Deterministic post-approval executor package (05-impl, task 5.4).

No LLM here. The runner replays the approved plan's actions in order,
exactly once each, via idempotent tool wrappers (``executor.tools``).

Layout (spec 05 §5)::

    backend/executor/
      __init__.py      this file (public surface + halt flags)
      config.py        MCP_MODE / tool URLs / backoff / timeout
      mcp_client.py    JSON-RPC ``tools/call`` with idempotency header
      runner.py        execute_plan() — order, skip-succeeded, retry, halt, audit
      tools/           one wrapper per side-effect tool (MCP↔direct-API swap contained)
"""

from __future__ import annotations

# In-memory halt (kill-switch) flags, keyed by case_id.
# Checked by the runner *between* actions; the in-flight tool call settles.
# Process-local by design for the single-worker pilot; a Redis key mirrors
# it when REDIS_URL is reachable (best-effort, never load-bearing).
HALT_REQUESTED: set[str] = set()


def request_halt(case_id: str) -> None:
    HALTED = HALT_REQUESTED
    HALTED.add(case_id)


def clear_halt(case_id: str) -> None:
    HALT_REQUESTED.discard(case_id)


def is_halt_requested(case_id: str) -> bool:
    return case_id in HALT_REQUESTED


__all__ = ["HALT_REQUESTED", "clear_halt", "is_halt_requested", "request_halt"]
