from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from packages.core.settings import Settings
from pydantic import ValidationError


def test_health_is_public_and_versioned(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0",
        "environment": "test",
    }


def test_ready_reports_ok(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"ok": {"status": "ok"}}}


def test_ready_returns_enveloped_503(failing_client: TestClient) -> None:
    response = failing_client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert body["error"]["details"]["checks"]["broken"]["status"] == "error"
    assert body["request_id"]


def test_settings_reject_missing_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DATABASE_URL",
        "REDIS_URL",
        "API_KEY_PEPPER",
        "JWT_SECRET",
        "WEBHOOK_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    text = str(exc_info.value)
    assert "database_url" in text
    assert "api_key_pepper" in text


def test_settings_reject_short_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql://u:p@localhost/db",
            redis_url="redis://localhost:6379/0",
            api_key_pepper="short",
            jwt_secret="b" * 40,
            webhook_secret_key="c" * 40,
        )


def test_settings_normalise_postgres_url(settings: Settings) -> None:
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.asyncpg_dsn.startswith("postgresql://")


def test_billing_requires_stripe_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql://u:p@localhost/db",
            redis_url="redis://localhost:6379/0",
            api_key_pepper="a" * 40,
            jwt_secret="b" * 40,
            webhook_secret_key="c" * 40,
            billing_enabled=True,
        )
