"""create_invite wrapper: {attendees, start, end} -> event id."""

from __future__ import annotations

TOOL_NAME = "create_invite"
REQUIRED_FIELDS = ("attendees", "start", "end")


def validate(payload: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "", [])]
    if missing:
        raise ValueError(f"create_invite missing required fields: {', '.join(missing)}")
    if not isinstance(payload.get("attendees"), list) or not payload["attendees"]:
        raise ValueError("create_invite 'attendees' must be a non-empty list")


async def run(key: str, client, **payload) -> str:
    validate(payload)
    result = await client.call_tool(
        TOOL_NAME,
        idempotency_key=key,
        args={"attendees": payload["attendees"], "start": payload["start"], "end": payload["end"]},
    )
    return result.external_ref
