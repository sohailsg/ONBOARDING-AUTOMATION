"""MCP JSON-RPC client for tool calls (05-impl, task 5.3).

Outbound contract (spec 05 §4): executor → MCP ``tools/call`` JSON-RPC with
the caller-supplied idempotency key carried on both the params and the
``Idempotency-Key`` header. Responses map to ``external_ref``
(message-id, ticket key, event id).

Sandbox behaviour: ``MCP_MODE=sandbox`` + loopback URLs use the in-process
fake transport (records calls, echoes the key, returns deterministic refs)
so unit/sandbox e2e never touch the network. Live mode uses httpx with a
20 s default timeout.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class McpCallResult:
    external_ref: str
    latency_ms: int
    raw: dict = field(default_factory=dict)


class FakeTransport:
    """In-process sandbox transport: records (tool, key, args), echoes key."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.failures: dict[str, int] = {}  # tool -> remaining transient failures

    def fail_next(self, tool: str, n: int = 1) -> None:
        self.failures[tool] = self.failures.get(tool, 0) + n

    async def call(self, tool: str, key: str, args: dict) -> McpCallResult:
        t0 = time.monotonic()
        self.calls.append({"tool": tool, "key": key, "args": dict(args)})
        remaining = self.failures.get(tool, 0)
        if remaining > 0:
            self.failures[tool] = remaining - 1
            raise TimeoutError(f"fake transient failure for {tool}")
        latency = int((time.monotonic() - t0) * 1000)
        return McpCallResult(
            external_ref=f"{tool}:{key}",
            latency_ms=latency,
            raw={"tool": tool, "idempotency_key_echo": key},
        )


class McpClient:
    """Thin JSON-RPC ``tools/call`` client with idempotency header."""

    def __init__(
        self,
        endpoint: str,
        *,
        mode: str = "sandbox",
        timeout: float = 20.0,
        transport: FakeTransport | None = None,
    ) -> None:
        from .config import assert_tool_url_allowed

        assert_tool_url_allowed(endpoint, mode)
        self.endpoint = endpoint
        self.mode = mode
        self.timeout = timeout
        self.transport = transport or FakeTransport()

    @property
    def is_fake(self) -> bool:
        return self.mode.strip().lower() == "sandbox"

    async def call_tool(self, tool: str, *, idempotency_key: str, args: dict | None = None) -> McpCallResult:
        payload_args = dict(args or {})
        if self.is_fake:
            return await self.transport.call(tool, idempotency_key, payload_args)
        import httpx

        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool, "arguments": payload_args, "idempotency_key": idempotency_key},
        }
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.post(
                self.endpoint,
                json=body,
                headers={"Idempotency-Key": idempotency_key, "X-Idempotency-Key": idempotency_key},
            )
            resp.raise_for_status()
            data = resp.json()
        latency = int((time.monotonic() - t0) * 1000)
        result = data.get("result", data) if isinstance(data, dict) else {}
        external_ref = (
            str(result.get("external_ref") or result.get("message_id") or result.get("ticket_key") or "")
            if isinstance(result, dict)
            else ""
        ) or f"{tool}:{idempotency_key}"
        return McpCallResult(external_ref=external_ref, latency_ms=latency, raw=data if isinstance(data, dict) else {})
