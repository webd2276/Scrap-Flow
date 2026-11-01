from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
from fastapi.testclient import TestClient
from packages.core.security import hash_password
from packages.core.settings import Settings
from tests.integration.conftest import auth_header, signup_payload


async def _fetchval(settings: Settings, query: str, *args: object) -> object:
    connection = await asyncpg.connect(settings.asyncpg_dsn)
    try:
        return await connection.fetchval(query, *args)
    finally:
        await connection.close()


async def _fetchrows(settings: Settings, query: str) -> list[asyncpg.Record]:
    connection = await asyncpg.connect(settings.asyncpg_dsn)
    try:
        return list(await connection.fetch(query))
    finally:
        await connection.close()


def test_signup_login_me_refresh_logout(client: TestClient) -> None:
    signup = client.post("/v1/auth/signup", json=signup_payload())
    assert signup.status_code == 201, signup.text
    body = signup.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "owner"
    assert body["refresh_token"] == client.cookies.get("sf_refresh")
    assert signup.headers["X-Request-ID"]
    assert "sf_refresh" in client.cookies

    me = client.get("/v1/auth/me", headers=auth_header(body["access_token"]))
    assert me.status_code == 200
    profile = me.json()
    assert profile["email"] == "owner@example.com"
    assert profile["orgs"][0]["role"] == "owner"
    assert profile["tos_version"]

    login = client.post(
        "/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["org_id"] == body["org_id"]

    old_refresh = client.cookies.get("sf_refresh")
    assert old_refresh
    rotated = client.post("/v1/auth/refresh")
    assert rotated.status_code == 200, rotated.text
    assert client.cookies.get("sf_refresh") != old_refresh

    replay = client.post("/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "UNAUTHORIZED"
    assert replay.json()["error"]["message"] == "Refresh token reuse detected"

    # Reuse revokes the whole family: the token from the legitimate rotation
    # is dead too, so a leaked token cannot be used alongside the victim.
    family = client.post("/v1/auth/refresh")
    assert family.status_code == 401

    logout = client.post("/v1/auth/logout")
    assert logout.status_code == 200
    assert client.cookies.get("sf_refresh") is None
    after = client.post("/v1/auth/refresh")
    assert after.status_code == 401


def test_signup_requires_tos_and_rejects_duplicates(client: TestClient) -> None:
    payload = signup_payload()
    payload["tos_accepted"] = False
    rejected = client.post("/v1/auth/signup", json=payload)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "VALIDATION_ERROR"

    assert client.post("/v1/auth/signup", json=signup_payload()).status_code == 201
    duplicate = client.post("/v1/auth/signup", json=signup_payload())
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CONFLICT"


def test_login_failure_is_generic(client: TestClient) -> None:
    client.post("/v1/auth/signup", json=signup_payload())
    response = client.post(
        "/v1/auth/login",
        json={"email": "owner@example.com", "password": "wrong password value"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password"

    unknown = client.post(
        "/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong password value"},
    )
    assert unknown.status_code == 401
    assert unknown.json()["error"]["message"] == "Invalid email or password"


def test_short_password_is_rejected(client: TestClient) -> None:
    payload = signup_payload()
    payload["password"] = "elevenchars"
    response = client.post("/v1/auth/signup", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_keys_are_hashed_scoped_and_revocable(
    client: TestClient, integration_settings: Settings
) -> None:
    signup = client.post("/v1/auth/signup", json=signup_payload()).json()
    token = signup["access_token"]

    created = client.post(
        "/v1/keys",
        headers=auth_header(token),
        json={"name": "CI key", "scopes": ["keys:manage", "jobs:read"]},
    )
    assert created.status_code == 201, created.text
    key_body = created.json()
    assert key_body["key"].startswith("sf_live_")
    assert key_body["prefix"] in key_body["key"]

    # The plaintext key never appears in a list response.
    listed = client.get("/v1/keys", headers=auth_header(token))
    assert listed.status_code == 200
    serialized = listed.text
    assert key_body["key"] not in serialized
    assert key_body["prefix"] in serialized

    # The key authenticates and last_used is updated.
    used = client.get("/v1/keys", headers={"X-API-Key": key_body["key"]})
    assert used.status_code == 200, used.text
    last_used = asyncio.run(
        _fetchval(
            integration_settings,
            "SELECT last_used_at FROM api_keys WHERE id = $1",
            key_body["id"],
        )
    )
    assert last_used is not None

    actions = asyncio.run(_fetchrows(integration_settings, "SELECT action FROM audit_logs"))
    assert {"org.created", "api_key.created"} <= {row["action"] for row in actions}

    revoked = client.delete(f"/v1/keys/{key_body['id']}", headers=auth_header(token))
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None

    after = client.get("/v1/keys", headers={"X-API-Key": key_body["key"]})
    assert after.status_code == 401


def test_key_scope_enforcement(client: TestClient) -> None:
    signup = client.post("/v1/auth/signup", json=signup_payload()).json()
    token = signup["access_token"]
    key = client.post(
        "/v1/keys",
        headers=auth_header(token),
        json={"name": "read only", "scopes": ["jobs:read"]},
    ).json()

    forbidden = client.get("/v1/keys", headers={"X-API-Key": key["key"]})
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"


def test_refuses_to_revoke_the_current_key(client: TestClient) -> None:
    signup = client.post("/v1/auth/signup", json=signup_payload()).json()
    token = signup["access_token"]
    key = client.post(
        "/v1/keys",
        headers=auth_header(token),
        json={"name": "self", "scopes": ["keys:manage"]},
    ).json()

    response = client.delete(f"/v1/keys/{key['id']}", headers={"X-API-Key": key["key"]})
    assert response.status_code == 409


def test_tenant_isolation_for_key_listing(client: TestClient) -> None:
    a = client.post(
        "/v1/auth/signup", json=signup_payload(email="a@example.com", org="Alpha")
    ).json()
    a_key = client.post(
        "/v1/keys",
        headers=auth_header(a["access_token"]),
        json={"name": "A", "scopes": ["keys:manage"]},
    ).json()

    b = client.post(
        "/v1/auth/signup", json=signup_payload(email="b@example.com", org="Beta")
    ).json()
    b_keys = client.get("/v1/keys", headers=auth_header(b["access_token"]))
    assert b_keys.status_code == 200
    assert b_keys.json() == []

    a_keys = client.get("/v1/keys", headers=auth_header(a["access_token"]))
    assert [item["id"] for item in a_keys.json()] == [a_key["id"]]


def test_missing_and_invalid_keys_are_401(client: TestClient) -> None:
    missing = client.get("/v1/keys")
    assert missing.status_code == 401
    invalid = client.get("/v1/keys", headers={"X-API-Key": "sf_live_bad_bad"})
    assert invalid.status_code == 401


def test_expired_key_rejected(client: TestClient, integration_settings: Settings) -> None:
    signup = client.post("/v1/auth/signup", json=signup_payload()).json()
    token = signup["access_token"]
    naive_future = client.post(
        "/v1/keys",
        headers=auth_header(token),
        json={
            "name": "naive expiry",
            "scopes": ["jobs:read"],
            "expires_at": "2030-01-01T00:00:00",
        },
    )
    assert naive_future.status_code == 201, naive_future.text
    naive_expiry = naive_future.json()["expires_at"]
    assert naive_expiry.endswith("Z") or "+00:00" in naive_expiry

    created = client.post(
        "/v1/keys",
        headers=auth_header(token),
        json={
            "name": "short",
            "scopes": ["jobs:read"],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    key = created.json()

    async def expire() -> None:
        connection = await asyncpg.connect(integration_settings.asyncpg_dsn)
        try:
            await connection.execute(
                "UPDATE api_keys SET expires_at = now() - interval '1 hour' WHERE id = $1",
                key["id"],
            )
        finally:
            await connection.close()

    asyncio.run(expire())
    rejected = client.get("/v1/keys", headers={"X-API-Key": key["key"]})
    assert rejected.status_code == 401


def test_key_cannot_grant_scopes_it_does_not_hold(client: TestClient) -> None:
    signup = client.post("/v1/auth/signup", json=signup_payload()).json()
    token = signup["access_token"]
    key = client.post(
        "/v1/keys",
        headers=auth_header(token),
        json={"name": "manager", "scopes": ["keys:manage"]},
    ).json()

    escalated = client.post(
        "/v1/keys",
        headers={"X-API-Key": key["key"]},
        json={"name": "escalated", "scopes": ["*"]},
    )
    assert escalated.status_code == 403
    assert escalated.json()["error"]["code"] == "FORBIDDEN"

    wider = client.post(
        "/v1/keys",
        headers={"X-API-Key": key["key"]},
        json={"name": "wider", "scopes": ["keys:manage", "billing:manage"]},
    )
    assert wider.status_code == 403

    allowed = client.post(
        "/v1/keys",
        headers={"X-API-Key": key["key"]},
        json={"name": "same", "scopes": ["keys:manage"]},
    )
    assert allowed.status_code == 201, allowed.text


def test_member_role_has_no_key_management(
    client: TestClient, integration_settings: Settings
) -> None:
    owner = client.post("/v1/auth/signup", json=signup_payload()).json()

    async def add_member() -> None:
        connection = await asyncpg.connect(integration_settings.asyncpg_dsn)
        try:
            user_id = uuid.uuid4()
            await connection.execute(
                "INSERT INTO users (id, email, password_hash, display_name, is_active, "
                "tos_accepted_at, tos_version) VALUES ($1, $2, $3, $4, true, now(), $5)",
                user_id,
                "member@example.com",
                hash_password("correct horse battery"),
                "Member",
                integration_settings.tos_version,
            )
            await connection.execute(
                "INSERT INTO memberships (id, org_id, user_id, role) VALUES ($1, $2, $3, $4)",
                uuid.uuid4(),
                uuid.UUID(owner["org_id"]),
                user_id,
                "member",
            )
        finally:
            await connection.close()

    asyncio.run(add_member())

    login = client.post(
        "/v1/auth/login",
        json={"email": "member@example.com", "password": "correct horse battery"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["role"] == "member"
    member_headers = auth_header(login.json()["access_token"])

    assert client.get("/v1/keys", headers=member_headers).status_code == 403
    assert (
        client.post(
            "/v1/keys",
            headers=member_headers,
            json={"name": "nope", "scopes": ["jobs:read"]},
        ).status_code
        == 403
    )
    assert client.get("/v1/auth/me", headers=member_headers).status_code == 200
