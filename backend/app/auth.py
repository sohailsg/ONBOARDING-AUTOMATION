"""JWT/RBAC deps. Stub behind AuthProvider interface (T-1) so SSO swap needs no route changes."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from jose import JWTError, jwt

from .config import Settings, get_settings


@dataclass
class TokenData:
    sub: str
    role: str  # employee | hr_admin | service


class AuthProvider:
    async def authenticate(self, request: Request) -> TokenData:  # pragma: no cover - interface
        raise NotImplementedError


def mint_dev_token(role: str, sub: str) -> str:
    """Test helper: dev bearer token parsed by StubAuthProvider."""
    return f"dev:{role}:{sub}"


def _decode_jwt(token: str, settings: Settings) -> TokenData:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            audience=settings.JWT_AUDIENCE or None,
            issuer=settings.JWT_ISSUER or None,
            options={"verify_aud": bool(settings.JWT_AUDIENCE), "verify_iss": bool(settings.JWT_ISSUER)},
        )
        sub = str(payload.get("sub", ""))
        role = str(payload.get("role", ""))
        if not sub or role not in ("employee", "hr_admin", "service"):
            raise JWTError("bad claims")
        return TokenData(sub=sub, role=role)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    settings: Settings = Depends(get_settings),
) -> TokenData:
    # 1) Service API key (n8n -> trigger). Accepted as X-Service-Key or Bearer <key>.
    service_key = settings.SERVICE_API_KEY
    bearer = (authorization or "").removeprefix("Bearer ").strip() if authorization else ""
    if x_service_key and x_service_key == service_key:
        return TokenData(sub="service", role="service")
    if bearer and bearer == service_key:
        return TokenData(sub="service", role="service")

    # 2) Dev stub tokens: "dev:<role>:<sub>" (no crypto; only when JWT_DEV_STUB=true).
    if settings.JWT_DEV_STUB and bearer.startswith("dev:"):
        try:
            _, role, sub = bearer.split(":", 2)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="malformed dev token") from exc
        if role not in ("employee", "hr_admin", "service") or not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad dev role")
        return TokenData(sub=sub, role=role)

    # 2b) Query token fallback for EventSource (T-3): ?token=<dev-or-jwt>
    q_token = request.query_params.get("token", "")
    if settings.JWT_DEV_STUB and q_token.startswith("dev:"):
        try:
            _, role, sub = q_token.split(":", 2)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="malformed dev token") from exc
        if role not in ("employee", "hr_admin", "service") or not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad dev role")
        return TokenData(sub=sub, role=role)
    if q_token and q_token == service_key:
        return TokenData(sub="service", role="service")

    # 3) Real JWT (HS256; swap AuthProvider/JWKS for SSO without route changes).
    if bearer:
        return _decode_jwt(bearer, settings)
    if q_token:
        return _decode_jwt(q_token, settings)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing credentials")


def require_roles(*roles: str):
    async def _dep(user: TokenData = Depends(get_current_user)) -> TokenData:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user

    return _dep
