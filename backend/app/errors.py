"""Spec §7 error map: 400 with Pydantic details; 5xx as JSON + Sentry capture."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def _validation_400(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.errors()})


async def _server_500(request: Request, exc: Exception) -> JSONResponse:
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_400)  # type: ignore[arg-type]
    # Fallback only: HTTPException / RateLimitExceeded keep their specific handlers.
    app.add_exception_handler(Exception, _server_500)
