"""create_notion_page wrapper: {template, owner} -> page id."""

from __future__ import annotations

TOOL_NAME = "create_notion_page"
REQUIRED_FIELDS = ("template", "owner")


def validate(payload: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if not str(payload.get(f, "")).strip()]
    if missing:
        raise ValueError(f"create_notion_page missing required fields: {', '.join(missing)}")


async def run(key: str, client, **payload) -> str:
    validate(payload)
    result = await client.call_tool(
        TOOL_NAME,
        idempotency_key=key,
        args={"template": payload["template"], "owner": payload["owner"]},
    )
    return result.external_ref
