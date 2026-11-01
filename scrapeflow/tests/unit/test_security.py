from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from packages.core.scopes import Scope, scopes_for_role, validate_scopes
from packages.core.security import (
    InvalidApiKeyError,
    TokenError,
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_password,
    hash_refresh_token,
    parse_api_key,
    verify_password,
    verify_secret,
)
from packages.core.settings import Settings
from pydantic import SecretStr, ValidationError


def test_api_key_format_and_verification(settings: Settings) -> None:
    generated = generate_api_key(settings.api_key_pepper.get_secret_value())
    assert generated.plaintext.startswith("sf_live_")
    parsed = parse_api_key(generated.plaintext)
    assert parsed.prefix == generated.prefix
    assert len(generated.prefix) == 8
    assert verify_secret(
        parsed.secret, generated.key_hash, settings.api_key_pepper.get_secret_value()
    )


def test_api_key_wrong_pepper_fails(settings: Settings) -> None:
    generated = generate_api_key(settings.api_key_pepper.get_secret_value())
    parsed = parse_api_key(generated.plaintext)
    assert not verify_secret(parsed.secret, generated.key_hash, "x" * 40)


def test_malformed_keys_are_rejected() -> None:
    for raw in ("", "nope", "sf_live_short_x", "sf_live_abcdefgh_", "other_abcdefgh_x" * 4):
        with pytest.raises(InvalidApiKeyError):
            parse_api_key(raw)


def test_password_hash_roundtrip() -> None:
    digest = hash_password("correct horse battery staple")
    assert digest != "correct horse battery staple"
    assert verify_password("correct horse battery staple", digest)
    assert not verify_password("wrong", digest)


def test_access_token_roundtrip(settings: Settings) -> None:
    user_id, org_id = uuid.uuid4(), uuid.uuid4()
    token, expires_in = create_access_token(settings, user_id=user_id, org_id=org_id, role="owner")
    claims = decode_access_token(settings, token)
    assert claims.user_id == user_id
    assert claims.org_id == org_id
    assert claims.role == "owner"
    assert expires_in == settings.jwt_access_ttl_seconds


def test_tampered_token_rejected(settings: Settings) -> None:
    token, _ = create_access_token(
        settings, user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="owner"
    )
    with pytest.raises(TokenError):
        decode_access_token(settings, token + "x")


def test_expired_token_rejected(settings: Settings) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "scrapeflow",
            "aud": "scrapeflow-api",
            "sub": str(uuid.uuid4()),
            "org": str(uuid.uuid4()),
            "role": "owner",
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "jti": uuid.uuid4().hex,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        decode_access_token(settings, token)


def test_refresh_hash_is_stable() -> None:
    assert hash_refresh_token("abc") == hash_refresh_token("abc")
    assert hash_refresh_token("abc") != hash_refresh_token("abd")


def test_scope_validation() -> None:
    assert validate_scopes(["jobs:read", "jobs:read"]) == ["jobs:read"]
    with pytest.raises(ValueError):
        validate_scopes(["jobs:read", "not-a-scope"])


def test_scope_values_are_stable() -> None:
    assert Scope.JOBS_READ.value == "jobs:read"
    assert Scope.ADMIN.value == "*"


def test_role_scope_matrix() -> None:
    for role in ("owner", "admin"):
        assert scopes_for_role(role) == {"*"}
    member = scopes_for_role("member")
    assert "jobs:read" in member
    assert "keys:manage" not in member
    assert "billing:manage" not in member


def test_access_token_has_kid(settings: Settings) -> None:
    token, _ = create_access_token(
        settings, user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="owner"
    )
    assert jwt.get_unverified_header(token)["kid"] == settings.jwt_active_kid


def test_jwt_key_rotation_accepts_previous_key(settings: Settings) -> None:
    old_token, _ = create_access_token(
        settings, user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="owner"
    )
    rotated = settings.model_copy(
        update={
            "jwt_active_kid": "v2",
            "jwt_previous_keys": SecretStr(
                json.dumps({"primary": settings.jwt_secret.get_secret_value()})
            ),
        }
    )
    assert decode_access_token(rotated, old_token).role == "owner"

    new_token, _ = create_access_token(
        rotated, user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="owner"
    )
    assert jwt.get_unverified_header(new_token)["kid"] == "v2"

    without_previous = rotated.model_copy(update={"jwt_previous_keys": None})
    with pytest.raises(TokenError):
        decode_access_token(without_previous, old_token)


def test_jwt_keyring_validation() -> None:
    base = {
        "_env_file": None,
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "api_key_pepper": "a" * 40,
        "jwt_secret": "b" * 40,
        "webhook_secret_key": "c" * 40,
    }
    with pytest.raises(ValidationError):
        Settings(**base, jwt_previous_keys=SecretStr("not-json"))
    with pytest.raises(ValidationError):
        Settings(**base, jwt_previous_keys=SecretStr(json.dumps({"old": "too-short"})))
    with pytest.raises(ValidationError):
        Settings(
            **base,
            jwt_active_kid="v1",
            jwt_previous_keys=SecretStr(json.dumps({"v1": "b" * 40})),
        )
