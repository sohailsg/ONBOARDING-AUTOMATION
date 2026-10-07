"""Rate limits (slowapi): chat 30/min/user, trigger 60/min/key, reindex 2/hr."""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _user_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    svc = request.headers.get("x-service-key", "") or request.headers.get("idempotency-key", "")
    who = auth[-12:] if auth else svc[-12:] if svc else get_remote_address(request)
    return f"{get_remote_address(request)}:{who}"


limiter = Limiter(key_func=_user_key)
