"""create_ticket wrapper: {queue, title, body} -> ticket key."""

from __future__ import annotations

TOOL_NAME = "create_ticket"
REQUIRED_FIELDS = ("queue", "title", "body")


def validate(payload: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if not str(payload.get(f, "")).strip()]
    if missing:
        raise ValueError(f"create_ticket missing required fields: {', '.join(missing)}")


async def run(key: str, client, **payload) -> str:
    validate(payload)
    result = await client.call_tool(
        TOOL_NAME,
        idempotency_key=key,
        args={"queue": payload["queue"], "title": payload["title"], "body": payload["body"]},
    )
    return result.external_ref
