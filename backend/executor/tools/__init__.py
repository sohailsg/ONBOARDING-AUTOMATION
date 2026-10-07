"""Per-tool wrappers (05-impl, task 5.3).

Each wrapper exposes ``TOOL_NAME``, ``REQUIRED_FIELDS`` and
``async def run(key, client, **payload) -> external_ref`` so the
MCP → direct-API swap stays contained behind this interface
(spec 05 §6 maintainability).

Payload schemas mirror spec 05 §7 + ``n8n/mcp_tools/*.json``.
"""

from __future__ import annotations

from . import calendar, email, hris, notion, slack, ticket

REGISTRY: dict[str, object] = {
    email.TOOL_NAME: email,
    slack.TOOL_NAME: slack,
    ticket.TOOL_NAME: ticket,
    hris.TOOL_NAME: hris,
    notion.TOOL_NAME: notion,
    calendar.TOOL_NAME: calendar,
}

ACTION_TYPES_V1: tuple[str, ...] = tuple(sorted(REGISTRY))

__all__ = ["ACTION_TYPES_V1", "REGISTRY", "calendar", "email", "hris", "notion", "slack", "ticket"]
