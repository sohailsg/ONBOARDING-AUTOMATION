"""Executor config (05-impl, tasks 5.1/5.4/5.6).

Sandbox enforcement (DoD): while ``MCP_MODE=sandbox`` the executor may only
talk to loopback tool URLs; any non-localhost URL raises. Production creds
must be absent in sandbox (see ``assert_sandbox_safe`` — covered by tests).
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from pydantic_settings import BaseSettings


BACKOFF_SECONDS: tuple[int, ...] = (2, 10, 60)
TOOL_TIMEOUT_SECONDS: float = 20.0
MAX_ATTEMPTS: int = 1 + len(BACKOFF_SECONDS)  # initial try + 3 retries


class ExecutorSettings(BaseSettings):
    model_config = {"env_prefix": "", "extra": "ignore"}

    MCP_MODE: str = "sandbox"  # sandbox | live
    NOTION_MCP_URL: str = "http://localhost:8002/mcp"
    CALENDAR_MCP_URL: str = "http://localhost:8003/mcp"
    N8N_MCP_URL: str = "http://localhost:5678/mcp"
    TOOL_TIMEOUT_SECONDS: float = TOOL_TIMEOUT_SECONDS
    EXECUTOR_CONCURRENCY: int = 5


@lru_cache
def get_executor_settings() -> ExecutorSettings:
    return ExecutorSettings()


def is_loopback(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1")


def assert_tool_url_allowed(url: str, mode: str) -> None:
    """Sandbox guard: sandbox mode talks to loopback tool URLs only."""
    if mode.strip().lower() == "sandbox" and not is_loopback(url):
        raise RuntimeError(f"sandbox mode: refusing non-loopback tool URL {url!r}")


def assert_sandbox_safe(mode: str, env: dict[str, str] | None = None) -> None:
    """Prod-cred absence test hook: sandbox must not carry live credentials.

    Raises if ``mode == "sandbox"`` while live-only credential vars are set.
    """
    import os

    if mode.strip().lower() != "sandbox":
        return
    live_vars = (
        "NOTION_API_KEY",
        "GOOGLE_CALENDAR_CREDENTIALS",
        "JIRA_API_TOKEN",
        "BAMBOOHR_API_KEY",
        "SLACK_BOT_TOKEN",
        "SMTP_PASSWORD",
    )
    source = env if env is not None else os.environ
    present = [v for v in live_vars if str(source.get(v, "")).strip()]
    if present:
        raise RuntimeError(f"sandbox mode: live credentials present: {', '.join(present)}")
