"""Worker settings — env-driven, free-stack only (no paid keys)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get(name: str, default: str) -> str:
    v = os.getenv(name, default)
    return v if v != "" else default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class WorkerSettings:
    ollama_host: str = field(default_factory=lambda: _get("OLLAMA_HOST", "http://localhost:11434"))
    chat_model: str = field(default_factory=lambda: _get("OLLAMA_CHAT_MODEL", "llama3.1:8b"))
    database_url: str = field(
        default_factory=lambda: _get("DATABASE_URL", "sqlite+aiosqlite:///./onboarding.db")
    )
    redis_url: str = field(default_factory=lambda: _get("REDIS_URL", "redis://localhost:6379/0"))
    rag_base_url: str = field(default_factory=lambda: _get("RAG_BASE_URL", "http://localhost:8001"))
    worker_concurrency: int = field(default_factory=lambda: _get_int("WORKER_CONCURRENCY", 4))
    max_steps_per_run: int = field(default_factory=lambda: _get_int("MAX_STEPS_PER_RUN", 12))
    max_tokens_per_run: int = field(default_factory=lambda: _get_int("MAX_TOKENS_PER_RUN", 30000))
    entitlement_cache_ttl_s: int = field(
        default_factory=lambda: _get_int("ENTITLEMENT_CACHE_TTL_S", 300)
    )
    prompt_version: str = field(default_factory=lambda: _get("PROMPT_VERSION", "v1"))
    langfuse_host: str = field(default_factory=lambda: _get("LANGFUSE_HOST", ""))
    langfuse_public_key: str = field(default_factory=lambda: _get("LANGFUSE_PUBLIC_KEY", ""))
    langfuse_secret_key: str = field(default_factory=lambda: _get("LANGFUSE_SECRET_KEY", ""))
    fixture_mode: str = field(default_factory=lambda: _get("WORKER_FIXTURE_MODE", ""))


_SETTINGS: WorkerSettings | None = None


def get_worker_settings() -> WorkerSettings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = WorkerSettings()
    return _SETTINGS


def reset_worker_settings() -> None:
    global _SETTINGS
    _SETTINGS = None
