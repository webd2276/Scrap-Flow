from __future__ import annotations

from apps.api.main import create_app
from fastapi.testclient import TestClient
from packages.core.settings import Settings
from tests.integration.conftest import OkProbe, auth_header, signup_payload


def test_auth_rate_limit_returns_429_with_headers(
    integration_settings: Settings,
) -> None:
    limited = integration_settings.model_copy(
        update={"rate_limit_auth_burst": 2, "rate_limit_auth_per_minute": 1}
    )
    app = create_app(limited, probes=[OkProbe()])
    with TestClient(app) as client:
        signup = client.post("/v1/auth/signup", json=signup_payload())
        assert signup.status_code == 201
        login = client.post(
            "/v1/auth/login",
            json={"email": "owner@example.com", "password": "correct horse battery"},
        )
        assert login.status_code == 200

        rejected = client.post(
            "/v1/auth/login",
            json={"email": "owner@example.com", "password": "correct horse battery"},
        )
        assert rejected.status_code == 429
        assert rejected.json()["error"]["code"] == "RATE_LIMITED"
        assert int(rejected.headers["Retry-After"]) >= 1
        assert rejected.headers["X-RateLimit-Remaining"] == "0"


def test_org_rate_limit_is_per_tenant(integration_settings: Settings) -> None:
    limited = integration_settings.model_copy(
        update={"rate_limit_org_burst": 2, "rate_limit_org_per_minute": 1}
    )
    app = create_app(limited, probes=[OkProbe()])
    with TestClient(app) as client:
        signup = client.post("/v1/auth/signup", json=signup_payload()).json()
        headers = auth_header(signup["access_token"])

        assert client.get("/v1/keys", headers=headers).status_code == 200
        assert client.get("/v1/keys", headers=headers).status_code == 200
        rejected = client.get("/v1/keys", headers=headers)
        assert rejected.status_code == 429
        assert rejected.json()["error"]["code"] == "RATE_LIMITED"
        assert rejected.headers["X-RateLimit-Limit"] == "2"


def test_other_tenant_has_own_bucket(integration_settings: Settings) -> None:
    limited = integration_settings.model_copy(
        update={"rate_limit_org_burst": 1, "rate_limit_org_per_minute": 1}
    )
    app = create_app(limited, probes=[OkProbe()])
    with TestClient(app) as client:
        a = client.post(
            "/v1/auth/signup", json=signup_payload(email="a@example.com", org="Alpha")
        ).json()
        b = client.post(
            "/v1/auth/signup", json=signup_payload(email="b@example.com", org="Beta")
        ).json()

        assert client.get("/v1/keys", headers=auth_header(a["access_token"])).status_code == 200
        assert client.get("/v1/keys", headers=auth_header(a["access_token"])).status_code == 429
        assert client.get("/v1/keys", headers=auth_header(b["access_token"])).status_code == 200
