"""send_email wrapper: {to, subject, body} -> message-id."""

from __future__ import annotations

TOOL_NAME = "send_email"
REQUIRED_FIELDS = ("to", "subject", "body")


def validate(payload: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if not str(payload.get(f, "")).strip()]
    if missing:
        raise ValueError(f"send_email missing required fields: {', '.join(missing)}")
    if "@" not in str(payload.get("to", "")):
        raise ValueError("send_email 'to' must be an email address")


async def run(key: str, client, **payload) -> str:
    validate(payload)
    result = await client.call_tool(
        TOOL_NAME,
        idempotency_key=key,
        args={"to": payload["to"], "subject": payload["subject"], "body": payload["body"]},
    )
    return result.external_ref
