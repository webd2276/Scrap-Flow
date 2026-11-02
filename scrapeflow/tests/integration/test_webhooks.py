from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import httpx
import respx
from apps.worker import job_store
from apps.worker.schedules import process_terminal_job
from apps.worker.webhooks import deliver_pending
from fastapi.testclient import TestClient
from packages.core.models import WebhookDeliveryStatus
from packages.core.settings import Settings
from packages.core.webhooks import verify_signature
from tests.integration.conftest import auth_header, signup_payload

PUBLIC_URL = "https://93.184.216.34/"
WEBHOOK_URL = "https://93.184.216.34/hook"
OTHER_WEBHOOK_URL = "https://93.184.216.34/other"


def _signup(client: TestClient, email: str = "owner@example.com", org: str = "Acme") -> str:
    response = client.post("/v1/auth/signup", json=signup_payload(email=email, org=org))
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _create_endpoint(
    client: TestClient,
    token: str,
    *,
    url: str = WEBHOOK_URL,
    **overrides: Any,
) -> dict[str, Any]:
    response = client.post(
        "/v1/webhooks",
        headers=auth_header(token),
        json={"url": url, "description": "test", **overrides},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _submit(client: TestClient, token: str, **overrides: Any) -> Any:
    return client.post(
        "/v1/scrape",
        headers=auth_header(token),
        json={"url": PUBLIC_URL, **overrides},
    )


async def _connect(settings: Settings) -> asyncpg.Connection:
    return await asyncpg.connect(settings.asyncpg_dsn)


async def _fetchrow(settings: Settings, query: str, *args: object) -> asyncpg.Record | None:
    connection = await _connect(settings)
    try:
        return await connection.fetchrow(query, *args)
    finally:
        await connection.close()


async def _execute(settings: Settings, query: str, *args: object) -> None:
    connection = await _connect(settings)
    try:
        await connection.execute(query, *args)
    finally:
        await connection.close()


async def _finish_job(settings: Settings, job_id: uuid.UUID) -> None:
    await _execute(
        settings,
        """
        UPDATE jobs
        SET status = 'succeeded', result = $2, finished_at = $3
        WHERE id = $1
        """,
        job_id,
        json.dumps({"title": "done"}),
        datetime.now(UTC),
    )


def _process(settings: Settings, job_id: uuid.UUID) -> None:
    async def run() -> None:
        maker = job_store.sessionmaker(settings)
        await process_terminal_job(maker, job_id=job_id, settings=settings)
        await job_store.dispose()

    asyncio.run(run())


def _deliver(settings: Settings) -> dict[str, int]:
    async def run() -> dict[str, int]:
        try:
            return await deliver_pending(settings=settings)
        finally:
            await job_store.dispose()

    return asyncio.run(run())


def _as_json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _prepare_delivery(
    client: TestClient,
    settings: Settings,
) -> tuple[str, dict[str, Any], uuid.UUID, uuid.UUID]:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    token = _signup(client, email=email, org=f"Acme {email}")
    endpoint = _create_endpoint(client, token)
    submitted = _submit(client, token)
    assert submitted.status_code == 202, submitted.text
    job_id = uuid.UUID(submitted.json()["job"]["id"])
    asyncio.run(_finish_job(settings, job_id))
    _process(settings, job_id)
    row = asyncio.run(
        _fetchrow(
            settings,
            "SELECT id FROM webhook_deliveries WHERE endpoint_id = $1",
            uuid.UUID(endpoint["endpoint"]["id"]),
        )
    )
    assert row is not None
    return token, endpoint, job_id, uuid.UUID(str(row["id"]))


def test_webhook_endpoint_lifecycle_secret_once_and_rotation(client: TestClient) -> None:
    token = _signup(client)
    first = _create_endpoint(client, token)
    assert first["secret"]
    assert first["endpoint"]["has_secret"] is True
    assert first["endpoint"]["events"] == ["job.cancelled", "job.completed", "job.failed"]

    second = _create_endpoint(client, token, url=OTHER_WEBHOOK_URL, events=["schedule.changed"])
    assert second["secret"] is None
    assert second["endpoint"]["has_secret"] is True

    listed = client.get("/v1/webhooks", headers=auth_header(token))
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 2
    assert all("secret" not in item for item in items)

    duplicate = client.post("/v1/webhooks", headers=auth_header(token), json={"url": WEBHOOK_URL})
    assert duplicate.status_code == 409, duplicate.text

    rotated = client.post("/v1/webhooks/rotate-secret", headers=auth_header(token))
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["secret"]
    assert rotated.json()["secret"] != first["secret"]

    endpoint_id = first["endpoint"]["id"]
    updated = client.patch(
        f"/v1/webhooks/{endpoint_id}",
        headers=auth_header(token),
        json={"description": "updated", "events": ["job.failed"], "enabled": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["description"] == "updated"
    assert updated.json()["events"] == ["job.failed"]
    assert updated.json()["enabled"] is False

    deliveries = client.get("/v1/webhooks/deliveries", headers=auth_header(token))
    assert deliveries.status_code == 200, deliveries.text
    assert deliveries.json()["total"] == 0

    other = _signup(client, email="other@example.com", org="Other")
    assert (
        client.patch(
            f"/v1/webhooks/{endpoint_id}",
            headers=auth_header(other),
            json={"description": "stolen"},
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/v1/webhooks/{endpoint_id}", headers=auth_header(other)).status_code == 404
    )
    assert client.post("/v1/webhooks/rotate-secret", headers=auth_header(other)).status_code == 200

    deleted = client.delete(f"/v1/webhooks/{endpoint_id}", headers=auth_header(token))
    assert deleted.status_code == 204
    remaining = client.get("/v1/webhooks", headers=auth_header(token))
    assert remaining.json()["total"] == 1


def test_webhook_url_validation_rejects_insecure_and_invalid_targets(client: TestClient) -> None:
    token = _signup(client)
    for url in (
        "http://93.184.216.34/hook",
        "https://127.0.0.1/hook",
        "https://169.254.169.254/latest/meta-data",
        "ftp://93.184.216.34/hook",
    ):
        response = client.post("/v1/webhooks", headers=auth_header(token), json={"url": url})
        assert response.status_code == 422, (url, response.text)

    invalid_events = client.post(
        "/v1/webhooks",
        headers=auth_header(token),
        json={"url": WEBHOOK_URL, "events": ["job.unknown"]},
    )
    assert invalid_events.status_code == 422


def test_webhook_url_requires_a_configured_signing_secret(client: TestClient) -> None:
    token = _signup(client)
    rejected = _submit(client, token, webhook_url=WEBHOOK_URL)
    assert rejected.status_code == 422, rejected.text
    assert "signing secret" in rejected.text

    _create_endpoint(client, token)
    accepted = _submit(client, token, webhook_url=WEBHOOK_URL)
    assert accepted.status_code == 202, accepted.text


def test_webhook_registry_is_bounded_per_org(client: TestClient) -> None:
    token = _signup(
        client,
        email=f"cap-{uuid.uuid4().hex[:8]}@example.com",
        org="Cap Org",
    )
    for index in range(20):
        created = client.post(
            "/v1/webhooks",
            headers=auth_header(token),
            json={"url": f"https://93.184.216.34/hook/{index}"},
        )
        assert created.status_code == 201, (index, created.text)

    overflow = client.post(
        "/v1/webhooks",
        headers=auth_header(token),
        json={"url": "https://93.184.216.34/hook/overflow"},
    )
    assert overflow.status_code == 422, overflow.text
    assert "at most 20" in overflow.text

    too_many_events = client.post(
        "/v1/webhooks",
        headers=auth_header(token),
        json={
            "url": "https://93.184.216.34/events",
            "events": ["job.completed"] * 5,
        },
    )
    assert too_many_events.status_code == 422, too_many_events.text


def test_terminal_job_enqueues_delivery_and_signed_http_post(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    _token, endpoint, job_id, delivery_id = _prepare_delivery(client, integration_settings)
    row = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT status, event_type, endpoint_id, payload FROM webhook_deliveries WHERE id = $1",
            delivery_id,
        )
    )
    assert row is not None
    assert row["status"] == "pending"
    assert row["event_type"] == "job.completed"
    assert str(row["endpoint_id"]) == endpoint["endpoint"]["id"]
    payload = _as_json(row["payload"])
    assert payload["type"] == "job.completed"
    assert payload["data"]["job_id"] == str(job_id)

    captured: dict[str, Any] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"ok": True})

    with respx.mock(assert_all_called=True) as router:
        router.post(WEBHOOK_URL).mock(side_effect=responder)
        result = _deliver(integration_settings)
    assert result == {"sent": 1, "retrying": 0, "dead": 0}

    signature = captured["headers"]["x-scrapeflow-signature"]
    timestamp = int(captured["headers"]["x-scrapeflow-timestamp"])
    assert captured["headers"]["x-scrapeflow-event"] == "job.completed"
    assert captured["headers"]["x-scrapeflow-delivery"] == str(delivery_id)
    assert verify_signature(
        endpoint["secret"],
        signature,
        timestamp,
        captured["body"],
        tolerance_seconds=300,
        now=timestamp,
    )
    assert json.loads(captured["body"])["data"]["job_id"] == str(job_id)

    stored = asyncio.run(
        _fetchrow(
            integration_settings,
            """
            SELECT status, attempts, response_status, delivered_at
            FROM webhook_deliveries WHERE id = $1
            """,
            delivery_id,
        )
    )
    assert stored is not None
    assert stored["status"] == "succeeded"
    assert stored["attempts"] == 1
    assert stored["response_status"] == 200
    assert stored["delivered_at"] is not None

    endpoint_row = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT last_success_at, last_failure_at FROM webhook_endpoints WHERE id = $1",
            uuid.UUID(endpoint["endpoint"]["id"]),
        )
    )
    assert endpoint_row is not None
    assert endpoint_row["last_success_at"] is not None
    assert endpoint_row["last_failure_at"] is None


def test_retry_then_success_and_non_retryable_dead_letter(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    _, _, _, delivery_id = _prepare_delivery(client, integration_settings)

    with respx.mock(assert_all_called=True) as router:
        router.post(WEBHOOK_URL).mock(return_value=httpx.Response(503, text="unavailable"))
        first = _deliver(integration_settings)
    assert first == {"sent": 0, "retrying": 1, "dead": 0}
    row = asyncio.run(
        _fetchrow(
            integration_settings,
            """
            SELECT status, attempts, response_status, next_attempt_at
            FROM webhook_deliveries WHERE id = $1
            """,
            delivery_id,
        )
    )
    assert row is not None
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert row["response_status"] == 503
    assert row["next_attempt_at"] > datetime.now(UTC)

    asyncio.run(
        _execute(
            integration_settings,
            "UPDATE webhook_deliveries SET next_attempt_at = $2 WHERE id = $1",
            delivery_id,
            datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    with respx.mock(assert_all_called=True) as router:
        router.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
        second = _deliver(integration_settings)
    assert second == {"sent": 1, "retrying": 0, "dead": 0}
    row = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT status, attempts FROM webhook_deliveries WHERE id = $1",
            delivery_id,
        )
    )
    assert row is not None
    assert row["status"] == "succeeded"
    assert row["attempts"] == 2

    _, _, _, dead_id = _prepare_delivery(client, integration_settings)
    with respx.mock(assert_all_called=True) as router:
        router.post(WEBHOOK_URL).mock(return_value=httpx.Response(400, text="bad request"))
        third = _deliver(integration_settings)
    assert third == {"sent": 0, "retrying": 0, "dead": 1}
    dead = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT status, attempts, error FROM webhook_deliveries WHERE id = $1",
            dead_id,
        )
    )
    assert dead is not None
    assert dead["status"] == WebhookDeliveryStatus.DEAD.value
    assert dead["attempts"] == 1
    assert "400" in str(dead["error"])


def test_enqueue_is_idempotent_per_job_event_and_url(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    _, _, job_id, _ = _prepare_delivery(client, integration_settings)
    _process(integration_settings, job_id)
    _process(integration_settings, job_id)
    row = asyncio.run(
        _fetchrow(
            integration_settings,
            """
            SELECT count(*) AS count FROM webhook_deliveries
            WHERE payload->'data'->>'job_id' = $1
            """,
            str(job_id),
        )
    )
    assert row is not None
    assert row["count"] == 1
