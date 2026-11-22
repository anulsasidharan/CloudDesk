"""JWT issue/verify and role checks (N1).

Tokens are HS256, signed with ``settings.effective_jwt_secret`` (the Supabase JWT secret when set,
otherwise ``JWT_SECRET``). The role ladder is ``viewer 1 < agent 2 < admin 3``. A token that does
not carry a known role is treated as ``viewer`` (least privilege); the service-role key never
appears in a token or a response.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.schemas.common import Role

ALGORITHM = "HS256"
AUDIENCE = "authenticated"  # what Supabase puts in ``aud``; we issue the same value
DEMO_TOKEN_TTL = timedelta(hours=8)
ROLE_LEVEL: dict[str, int] = {Role.VIEWER.value: 1, Role.AGENT.value: 2, Role.ADMIN.value: 3}

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthUser:
    """The caller, as proven by a verified token."""

    id: str
    email: str
    role: str

    def has_role(self, minimum: Role | str) -> bool:
        return ROLE_LEVEL.get(self.role, 0) >= ROLE_LEVEL[Role(minimum).value]


class TokenError(Exception):
    """The token is missing, malformed, expired, or signed with the wrong key."""


class SecretNotConfiguredError(RuntimeError):
    """No JWT secret is configured, so tokens can neither be issued nor trusted."""


def _secret() -> str:
    secret = get_settings().effective_jwt_secret
    if not secret:
        raise SecretNotConfiguredError("JWT_SECRET is not set")
    return secret


def create_access_token(
    *,
    user_id: str,
    email: str,
    role: Role | str,
    ttl: timedelta = DEMO_TOKEN_TTL,
    now: datetime | None = None,
) -> str:
    """Sign a token for ``user_id``. ``role`` must be one of the three known roles."""
    issued = now or datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": user_id,
        "email": email.strip().lower(),
        "role": Role(role).value,
        "aud": AUDIENCE,
        "iat": issued,
        "exp": issued + ttl,
    }
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM)


def _role_from_claims(claims: dict[str, Any]) -> str:
    """Our ``role`` claim, or Supabase's ``app_metadata.role``; anything else is a viewer."""
    candidates = [claims.get("role")]
    app_metadata = claims.get("app_metadata")
    if isinstance(app_metadata, dict):
        candidates.append(app_metadata.get("role"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate in ROLE_LEVEL:
            return candidate
    return Role.VIEWER.value


def decode_token(token: str) -> AuthUser:
    """Verify signature, audience and expiry. Raises ``TokenError`` for any failure."""
    try:
        secret = _secret()
    except SecretNotConfiguredError as exc:
        raise TokenError("auth is not configured") from exc
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("invalid or expired token") from exc
    return AuthUser(
        id=str(claims["sub"]),
        email=str(claims.get("email", "")),
        role=_role_from_claims(claims),
    )


def bearer_token(authorization: str | None) -> str | None:
    """Pull the token out of an ``Authorization: Bearer <token>`` header value."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    """FastAPI dependency: 401 without a valid bearer token."""
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_role(minimum: Role | str) -> Callable[[AuthUser], AuthUser]:
    """Dependency factory: 401 without a token, 403 when the role is below ``minimum``."""
    needed = Role(minimum)

    def dependency(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if not user.has_role(needed):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role {needed.value} or higher")
        return user

    return dependency
