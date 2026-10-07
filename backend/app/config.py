"""Backend gateway settings (02-impl task 2.1)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./onboarding.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    RAG_BASE_URL: str = "http://localhost:8001"
    JWT_DEV_STUB: bool = True
    JWT_SECRET: str = "dev-only-change-me"
    JWT_ISSUER: str = ""
    JWT_AUDIENCE: str = ""
    SERVICE_API_KEY: str = "dev-service-key"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    ARQ_QUEUE: str = "default"
    SENTRY_DSN: str = ""
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    ENV: str = "dev"
    LANGFUSE_HOST: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    # 7.2 retention (months). Legal confirms N; strictest default ships first.
    CHAT_RETENTION_MONTHS: int = 12
    TRACE_RETENTION_MONTHS: int = 6
    RETENTION_DRY_RUN: bool = True

    def validate_production(self) -> list[str]:
        """7.1 pilot gate: prod/staging must not run on dev defaults.

        Returns a list of blocking findings (empty = safe to promote).
        """
        if self.ENV not in ("staging", "prod", "pilot"):
            return []
        problems: list[str] = []
        if self.JWT_DEV_STUB:
            problems.append("JWT_DEV_STUB must be false in staging/pilot/prod")
        if self.JWT_SECRET in ("", "dev-only-change-me"):
            problems.append("JWT_SECRET must be set from the secret manager")
        if self.SERVICE_API_KEY in ("", "dev-service-key"):
            problems.append("SERVICE_API_KEY must be set from the secret manager")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
