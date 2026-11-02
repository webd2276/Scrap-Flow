from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from fastapi.testclient import TestClient
from packages.core.settings import Settings
from tests.integration.conftest import RecordingDispatcher, auth_header, signup_payload

PUBLIC_URL = "https://93.184.216.34/"


def _signup(client: TestClient, email: str = "owner@example.com", org: str = "Acme") -> str:
    response = client.post("/v1/auth/signup", json=signup_payload(email=email, org=org))
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _submit(
    client: TestClient,
    token: str,
    *,
    headers: dict[str, str] | None = None,
    **overrides: Any,
) -> Any:
    payload = {"url": PUBLIC_URL, **overrides}
    merged = auth_header(token) | (headers or {})
    return client.post("/v1/scrape", headers=merged, json=payload)


def test_submit_get_list_events_and_cancel(
    client: TestClient, dispatcher: RecordingDispatcher
) -> None:
    token = _signup(client)
    response = _submit(client, token, selectors={"title": {"css": "title"}})
    assert response.status_code == 202, response.text
    body = response.json()
    job = body["job"]
    job_id = uuid.UUID(job["id"])
    assert body["deduplicated"] is False
    assert job["status"] == "queued"
    assert job["kind"] == "scrape"
    assert dispatcher.enqueued == [job_id]

    fetched = client.get(f"/v1/jobs/{job_id}", headers=auth_header(token))
    assert fetched.status_code == 200
    assert fetched.json()["id"] == str(job_id)

    listed = client.get("/v1/jobs", headers=auth_header(token))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == str(job_id)

    filtered = client.get("/v1/jobs?status=succeeded", headers=auth_header(token))
    assert filtered.json()["total"] == 0

    events = client.get(f"/v1/jobs/{job_id}/events", headers=auth_header(token))
    assert events.status_code == 200
    assert events.json()[0]["type"] == "queued"

    cancelled = client.post(f"/v1/jobs/{job_id}/cancel", headers=auth_header(token))
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"
    assert cancelled.json()["job"]["finished_at"]


def test_idempotency_replays_the_same_job(
    client: TestClient, dispatcher: RecordingDispatcher
) -> None:
    token = _signup(client)
    headers = {"Idempotency-Key": "request-123"}
    first = _submit(client, token, headers=headers)
    second = _submit(client, token, headers=headers)
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.headers["Idempotent-Replay"] == "true"
    assert second.json()["deduplicated"] is True
    assert first.json()["job"]["id"] == second.json()["job"]["id"]
    assert len(dispatcher.enqueued) == 1


def test_invalid_idempotency_key_is_rejected(client: TestClient) -> None:
    token = _signup(client)
    response = _submit(client, token, headers={"Idempotency-Key": "bad key!"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_ssrf_and_policy_validation(client: TestClient, dispatcher: RecordingDispatcher) -> None:
    token = _signup(client)
    for url in (
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://[::1]/",
        "http://224.0.0.1/",
    ):
        response = client.post("/v1/scrape", headers=auth_header(token), json={"url": url})
        assert response.status_code == 422, url
        assert response.json()["error"]["code"] == "BLOCKED_URL", url

    invalid = client.post(
        "/v1/scrape", headers=auth_header(token), json={"url": "file:///etc/passwd"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] in {"VALIDATION_ERROR", "INVALID_URL"}

    insecure_webhook = _submit(client, token, webhook_url="http://93.184.216.34/hook")
    assert insecure_webhook.status_code == 422
    assert insecure_webhook.json()["error"]["code"] == "VALIDATION_ERROR"

    proxy = _submit(client, token, proxy_country="de")
    assert proxy.status_code == 422
    assert "not available" in proxy.json()["error"]["message"]

    screenshot = _submit(client, token, screenshot=True)
    assert screenshot.status_code == 422
    assert dispatcher.enqueued == []


def test_tenant_isolation(client: TestClient) -> None:
    first = _signup(client, email="one@example.com", org="One")
    second = _signup(client, email="two@example.com", org="Two")
    job_id = _submit(client, first).json()["job"]["id"]

    assert client.get(f"/v1/jobs/{job_id}", headers=auth_header(second)).status_code == 404
    assert client.post(f"/v1/jobs/{job_id}/cancel", headers=auth_header(second)).status_code == 404
    assert client.get(f"/v1/jobs/{job_id}/events", headers=auth_header(second)).status_code == 404
    assert client.get("/v1/jobs", headers=auth_header(second)).json()["total"] == 0


def test_scope_enforcement(client: TestClient) -> None:
    token = _signup(client)
    reader = client.post(
        "/v1/keys",
        headers=auth_header(token),
        json={"name": "reader", "scopes": ["jobs:read"]},
    ).json()["key"]
    writer = client.post(
        "/v1/keys",
        headers=auth_header(token),
        json={"name": "writer", "scopes": ["scrape:write"]},
    ).json()["key"]

    denied = client.post("/v1/scrape", headers={"X-API-Key": reader}, json={"url": PUBLIC_URL})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    allowed = client.post("/v1/scrape", headers={"X-API-Key": writer}, json={"url": PUBLIC_URL})
    assert allowed.status_code == 202

    assert client.get("/v1/jobs", headers={"X-API-Key": writer}).status_code == 403
    assert (
        client.post(
            "/v1/jobs",
            headers={"X-API-Key": reader},
            json={"url": PUBLIC_URL},
        ).status_code
        == 405
    )


def test_artifact_listing_and_download(client: TestClient, integration_settings: Settings) -> None:
    token = _signup(client)
    job_id = uuid.UUID(_submit(client, token).json()["job"]["id"])

    store = client.app.state.artifact_store
    org_id = asyncio.run(
        _fetchval(
            integration_settings,
            "SELECT org_id FROM jobs WHERE id = $1",
            job_id,
        )
    )
    assert org_id is not None
    stored = store.put(
        org_id=org_id,
        job_id=job_id,
        filename="screenshot.png",
        content_type="image/png",
        data=b"\x89PNG-data",
    )

    async def insert() -> uuid.UUID:
        connection = await asyncpg.connect(integration_settings.asyncpg_dsn)
        try:
            artifact_id = uuid.uuid4()
            await connection.execute(
                "INSERT INTO artifacts (id, org_id, job_id, kind, filename, content_type, "
                "size_bytes, sha256, storage_key, expires_at) "
                "VALUES ($1, $2, $3, 'screenshot', 'screenshot.png', 'image/png', "
                "$4, $5, $6, $7)",
                artifact_id,
                org_id,
                job_id,
                stored.size_bytes,
                stored.sha256,
                stored.storage_key,
                datetime.now(UTC) + timedelta(days=1),
            )
            return artifact_id
        finally:
            await connection.close()

    artifact_id = asyncio.run(insert())

    listed = client.get(f"/v1/jobs/{job_id}/artifacts", headers=auth_header(token))
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["filename"] == "screenshot.png"
    assert listed.json()[0]["download_url"] == f"/v1/artifacts/{artifact_id}/download"

    download = client.get(f"/v1/artifacts/{artifact_id}/download", headers=auth_header(token))
    assert download.status_code == 200
    assert download.content == b"\x89PNG-data"
    assert download.headers["content-type"] == "image/png"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"


async def _fetchval(settings: Settings, query: str, *args: object) -> object:
    connection = await asyncpg.connect(settings.asyncpg_dsn)
    try:
        return await connection.fetchval(query, *args)
    finally:
        await connection.close()
