from __future__ import annotations

from typing import Any

import pytest
from packages.core.secretbox import (
    SecretBoxError,
    encryption_key,
    open_secrets,
    seal_secrets,
)
from packages.core.settings import Settings


def _settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        api_key_pepper="a" * 40,
        jwt_secret="b" * 40,
        webhook_secret_key="c" * 40,
        **overrides,
    )


def test_seal_and_open_roundtrip() -> None:
    settings = _settings()
    key = encryption_key(settings)
    token = seal_secrets({"user": "alice"}, key=key, associated_data=b"job-1")
    assert "alice" not in token
    assert open_secrets(token, key=key, associated_data=b"job-1") == {"user": "alice"}


def test_dedicated_key_changes_ciphertext_key() -> None:
    default = encryption_key(_settings())
    dedicated = encryption_key(_settings(automation_secret_key="d" * 40))
    assert default != dedicated


def test_tampering_and_wrong_job_are_rejected() -> None:
    settings = _settings()
    key = encryption_key(settings)
    token = seal_secrets({"user": "alice"}, key=key, associated_data=b"job-1")

    with pytest.raises(SecretBoxError):
        open_secrets(token, key=key, associated_data=b"job-2")
    with pytest.raises(SecretBoxError):
        open_secrets(token, key=b"x" * 32, associated_data=b"job-1")
    with pytest.raises(SecretBoxError):
        open_secrets("not-base64!", key=key, associated_data=b"job-1")
    with pytest.raises(SecretBoxError):
        open_secrets("", key=key, associated_data=b"job-1")


def test_tampered_ciphertext_is_rejected() -> None:
    settings = _settings()
    key = encryption_key(settings)
    token = seal_secrets({"user": "alice"}, key=key, associated_data=b"job-1")
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(SecretBoxError):
        open_secrets(tampered, key=key, associated_data=b"job-1")
