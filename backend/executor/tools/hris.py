"""write_hris wrapper: {employee_id, fields} -> hris record ref."""

from __future__ import annotations

TOOL_NAME = "write_hris"
REQUIRED_FIELDS = ("employee_id", "fields")


def validate(payload: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "", {})]
    if missing:
        raise ValueError(f"write_hris missing required fields: {', '.join(missing)}")
    if not isinstance(payload.get("fields"), dict):
        raise ValueError("write_hris 'fields' must be an object")


async def run(key: str, client, **payload) -> str:
    validate(payload)
    result = await client.call_tool(
        TOOL_NAME,
        idempotency_key=key,
        args={"employee_id": payload["employee_id"], "fields": payload["fields"]},
    )
    return result.external_ref
