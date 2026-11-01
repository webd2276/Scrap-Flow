"""JWT access tokens and opaque refresh tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from packages.core.settings import Settings

ISSUER = "scrapeflow"
AUDIENCE = "scrapeflow-api"
ALGORITHM = "HS256"


class TokenError(ValueError):
    """Token is missing, expired, malformed, or of the wrong type."""


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str
    jti: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RefreshTokenValue:
    plaintext: str
    token_hash: str
    expires_at: datetime


def create_access_token(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=settings.jwt_access_ttl_seconds)
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_id),
        "org": str(org_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": expires,
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=ALGORITHM,
        headers={"kid": settings.jwt_active_kid},
    )
    return token, settings.jwt_access_ttl_seconds


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid or expired access token") from exc

    kid = str(header.get("kid") or settings.jwt_active_kid)
    signing_key = settings.jwt_keyring.get(kid)
    if signing_key is None:
        raise TokenError("Unknown token signing key")

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "org", "type", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid or expired access token") from exc

    if payload.get("type") != "access":
        raise TokenError("Wrong token type")

    try:
        return AccessClaims(
            user_id=uuid.UUID(str(payload["sub"])),
            org_id=uuid.UUID(str(payload["org"])),
            role=str(payload["role"]),
            jti=str(payload["jti"]),
            expires_at=datetime.fromtimestamp(float(payload["exp"]), tz=UTC),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenError("Malformed access token claims") from exc


def generate_refresh_token(settings: Settings) -> RefreshTokenValue:
    plaintext = secrets.token_urlsafe(48)
    return RefreshTokenValue(
        plaintext=plaintext,
        token_hash=hash_refresh_token(plaintext),
        expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_ttl_days),
    )


def hash_refresh_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()
