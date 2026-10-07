"""FastAPI gateway (02-impl): auth/RBAC, §7 REST + SSE, Arq enqueue, audit. No LLM logic."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from slowapi.errors import RateLimitExceeded

from .config import get_settings
from .db import get_engine
from .metrics import observe_request, render_prometheus
from .models import Base
from .ratelimit import limiter
from .routers import admin, approvals, cases, chat, execute, me, onboarding, plans

log = logging.getLogger("onboarding.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk

            sentry_sdk.init(dsn=settings.SENTRY_DSN)
        except Exception as exc:  # pragma: no cover
            log.warning("sentry init failed: %s", exc)
    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:  # pragma: no cover
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider()
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)))
            trace.set_tracer_provider(provider)
        except Exception as exc:
            log.warning("otel init failed: %s", exc)
    # Create tables if missing (01 owns migrations; gateway is tolerant for dev/tests).
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        log.warning("db init skipped: %s", exc)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Onboarding Gateway API", version="0.2.0-w2", lifespan=lifespan)
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _ratelimit(request: Request, exc: RateLimitExceeded):
        return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> PlainTextResponse:
        from . import jobs as _jobs

        return PlainTextResponse(render_prometheus(_jobs.dlq_depth()), media_type="text/plain")

    @app.middleware("http")
    async def _metrics_middleware(request: Request, call_next):  # 7.4 latency series
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        except Exception:
            observe_request(request.url.path, "500", (time.perf_counter() - start) * 1000)
            raise
        else:
            observe_request(request.url.path, status, (time.perf_counter() - start) * 1000)

    app.include_router(onboarding.router)
    app.include_router(cases.router)
    app.include_router(plans.router)
    app.include_router(approvals.router)
    app.include_router(me.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    app.include_router(execute.router)
    return app


app = create_app()
