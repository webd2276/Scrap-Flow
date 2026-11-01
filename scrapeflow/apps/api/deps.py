"""Request authentication, scope enforcement, and rate-limit dependencies."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from packages.core.db import get_db
from packages.core.errors import AppError, ErrorCode
from packages.core.models import ApiKey, Membership, Organization, User
from packages.core.rate_limit import RateLimiter
from packages.core.redis import get_redis
from packages.core.scopes import Scope, scopes_for_role
from packages.core.security import (
    InvalidApiKeyError,
    TokenError,
    decode_access_token,
    parse_api_key,
    verify_secret,
)
from packages.core.settings import Settings
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class AuthContext:
    org_id: uuid.UUID
    user_id: uuid.UUID | None
    api_key_id: uuid.UUID | None
    role: str
    scopes: frozenset[str]
    auth_method: str
    plan: str


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def hash_ip(ip: str, pepper: str) -> str:
    return hashlib.sha256(f"{pepper}{ip}".encode()).hexdigest()


def _has_scope(context: AuthContext, scope: Scope) -> bool:
    return Scope.ADMIN.value in context.scopes or scope.value in context.scopes


def can_grant_scopes(context: AuthContext, requested: list[str]) -> bool:
    """Callers may only mint keys with scopes they already hold."""
    if Scope.ADMIN.value in context.scopes:
        return True
    return set(requested).issubset(context.scopes)


async def get_api_key_auth(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> AuthContext:
    if not x_api_key:
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Missing X-API-Key header")
    try:
        parsed = parse_api_key(x_api_key)
    except InvalidApiKeyError as exc:
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Invalid API key") from exc

    row = (
        await db.execute(
            select(ApiKey, Organization)
            .join(Organization, Organization.id == ApiKey.org_id)
            .where(ApiKey.prefix == parsed.prefix)
        )
    ).one_or_none()
    if row is None:
        # Keep the response time similar to a real prefix hit.
        verify_secret(parsed.secret, "0" * 64, settings.api_key_pepper.get_secret_value())
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Invalid API key")

    api_key, org = row
    now = datetime.now(UTC)
    if (
        api_key.revoked_at is not None
        or (api_key.expires_at is not None and api_key.expires_at <= now)
        or not verify_secret(
            parsed.secret, api_key.key_hash, settings.api_key_pepper.get_secret_value()
        )
    ):
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Invalid API key")

    if api_key.last_used_at is None or (now - api_key.last_used_at).total_seconds() > 60:
        await db.execute(update(ApiKey).where(ApiKey.id == api_key.id).values(last_used_at=now))
        await db.commit()

    return AuthContext(
        org_id=org.id,
        user_id=None,
        api_key_id=api_key.id,
        role="api_key",
        scopes=frozenset(api_key.scopes),
        auth_method="api_key",
        plan=org.plan.value,
    )


async def get_jwt_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> AuthContext:
    if credentials is None:
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Missing bearer token")
    try:
        claims = decode_access_token(settings, credentials.credentials)
    except TokenError as exc:
        raise AppError(401, ErrorCode.UNAUTHORIZED, str(exc)) from exc

    user = await db.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Invalid session")

    membership = (
        await db.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.org_id)
            .where(Membership.user_id == user.id, Membership.org_id == claims.org_id)
        )
    ).one_or_none()
    if membership is None:
        raise AppError(403, ErrorCode.FORBIDDEN, "No access to this organization")

    member, org = membership
    return AuthContext(
        org_id=org.id,
        user_id=user.id,
        api_key_id=None,
        role=member.role.value,
        scopes=scopes_for_role(member.role.value),
        auth_method="jwt",
        plan=org.plan.value,
    )


async def get_auth(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> AuthContext:
    if x_api_key:
        return await get_api_key_auth(x_api_key, db, settings)
    if credentials is not None:
        return await get_jwt_auth(credentials, db, settings)
    raise AppError(401, ErrorCode.UNAUTHORIZED, "Authentication required")


def require_scope(scope: Scope) -> Callable[..., Awaitable[AuthContext]]:
    async def dependency(context: AuthContext = Depends(get_auth)) -> AuthContext:
        if not _has_scope(context, scope):
            raise AppError(403, ErrorCode.FORBIDDEN, f"Missing scope: {scope.value}")
        return context

    return dependency


async def org_rate_limit(
    response: Response,
    context: AuthContext = Depends(get_auth),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
) -> None:
    limiter = RateLimiter(redis)
    try:
        result = await limiter.consume(
            f"rl:org:{context.org_id}",
            capacity=settings.rate_limit_org_burst,
            refill_per_second=settings.rate_limit_org_per_minute / 60,
        )
    except Exception as exc:  # fail closed: never silently disable limits
        raise AppError(503, ErrorCode.SERVICE_UNAVAILABLE, "Rate limiter unavailable") from exc

    response.headers.update(result.headers())
    if not result.allowed:
        raise AppError(
            429,
            ErrorCode.RATE_LIMITED,
            "Rate limit exceeded",
            headers=result.headers(),
        )


async def ip_rate_limit(
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
) -> None:
    limiter = RateLimiter(redis)
    try:
        result = await limiter.consume(
            f"rl:ip:{client_ip(request)}",
            capacity=settings.rate_limit_ip_burst,
            refill_per_second=settings.rate_limit_ip_per_minute / 60,
        )
    except Exception as exc:
        raise AppError(503, ErrorCode.SERVICE_UNAVAILABLE, "Rate limiter unavailable") from exc

    response.headers.update(result.headers())
    if not result.allowed:
        raise AppError(429, ErrorCode.RATE_LIMITED, "Rate limit exceeded", headers=result.headers())


async def auth_ip_rate_limit(
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
) -> None:
    limiter = RateLimiter(redis)
    try:
        result = await limiter.consume(
            f"rl:auth-ip:{client_ip(request)}",
            capacity=settings.rate_limit_auth_burst,
            refill_per_second=settings.rate_limit_auth_per_minute / 60,
        )
    except Exception as exc:
        raise AppError(503, ErrorCode.SERVICE_UNAVAILABLE, "Rate limiter unavailable") from exc

    response.headers.update(result.headers())
    if not result.allowed:
        raise AppError(
            429,
            ErrorCode.RATE_LIMITED,
            "Too many authentication attempts",
            headers=result.headers(),
        )
