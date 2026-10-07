"""post_slack wrapper: {channel, text} -> message ts."""

from __future__ import annotations

TOOL_NAME = "post_slack"
REQUIRED_FIELDS = ("channel", "text")


def validate(payload: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if not str(payload.get(f, "")).strip()]
    if missing:
        raise ValueError(f"post_slack missing required fields: {', '.join(missing)}")


async def run(key: str, client, **payload) -> str:
    validate(payload)
    result = await client.call_tool(
        TOOL_NAME,
        idempotency_key=key,
        args={"channel": payload["channel"], "text": payload["text"]},
    )
    return result.external_ref
