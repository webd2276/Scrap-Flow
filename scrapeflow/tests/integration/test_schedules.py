from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from apps.worker import job_store
from apps.worker.schedules import dispatch_due_schedules, process_terminal_job
from fastapi.testclient import TestClient
from packages.core.quota import QuotaStore
from packages.core.settings import Settings
from redis.asyncio import Redis
from tests.integration.conftest import RecordingDispatcher, auth_header, signup_payload

PUBLIC_URL = "https://93.184.216.34/"
WEBHOOK_URL = "https://93.184.216.34/hook"


def _signup(client: TestClient, email: str = "owner@example.com", org: str = "Acme") -> str:
    response = client.post("/v1/auth/signup", json=signup_payload(email=email, org=org))
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _schedule_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Daily homepage",
        "kind": "scrape",
        "cron": "0 9 * * *",
        "timezone": "UTC",
        "enabled": True,
        "template": {"url": PUBLIC_URL},
        "watched_fields": ["title"],
        "notify_on_change": True,
    }
    payload.update(overrides)
    return payload


def _create_schedule(client: TestClient, token: str, **overrides: Any) -> dict[str, Any]:
    response = client.post(
        "/v1/schedules", headers=auth_header(token), json=_schedule_payload(**overrides)
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def _connect(settings: Settings) -> asyncpg.Connection:
    return await asyncpg.connect(settings.asyncpg_dsn)


async def _fetchrow(settings: Settings, query: str, *args: object) -> asyncpg.Record | None:
    connection = await _connect(settings)
    try:
        return await connection.fetchrow(query, *args)
    finally:
        await connection.close()


async def _fetchval(settings: Settings, query: str, *args: object) -> object:
    connection = await _connect(settings)
    try:
        return await connection.fetchval(query, *args)
    finally:
        await connection.close()


async def _execute(settings: Settings, query: str, *args: object) -> None:
    connection = await _connect(settings)
    try:
        await connection.execute(query, *args)
    finally:
        await connection.close()


async def _due(settings: Settings, schedule_id: uuid.UUID, *, seconds_ago: int = 5) -> None:
    await _execute(
        settings,
        "UPDATE schedules SET next_run_at = $2 WHERE id = $1",
        schedule_id,
        datetime.now(UTC) - timedelta(seconds=seconds_ago),
    )


async def _finish_job(
    settings: Settings,
    job_id: uuid.UUID,
    *,
    result: dict[str, Any],
    status: str = "succeeded",
) -> None:
    await _execute(
        settings,
        """
        UPDATE jobs
        SET status = $2, result = $3, finished_at = $4, error_code = NULL, error_message = NULL
        WHERE id = $1
        """,
        job_id,
        status,
        json.dumps(result),
        datetime.now(UTC),
    )


def _dispatch(
    settings: Settings,
    *,
    dispatched: list[uuid.UUID],
) -> dict[str, int]:
    async def run() -> dict[str, int]:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            return await dispatch_due_schedules(
                settings=settings,
                redis=redis,
                dispatch_job=dispatched.append,
            )
        finally:
            await redis.aclose()
            await job_store.dispose()

    return asyncio.run(run())


def _process(settings: Settings, job_id: uuid.UUID) -> None:
    async def run() -> None:
        maker = job_store.sessionmaker(settings)
        await process_terminal_job(maker, job_id=job_id, settings=settings)
        await job_store.dispose()

    asyncio.run(run())


def _release_slot(settings: Settings, org_id: uuid.UUID, job_id: uuid.UUID) -> None:
    async def run() -> None:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await QuotaStore(redis).release_slot(org_id, job_id=job_id)
        finally:
            await redis.aclose()

    asyncio.run(run())


def _as_json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def test_schedule_crud_validation_and_tenant_isolation(client: TestClient) -> None:
    token = _signup(client)
    created = _create_schedule(client, token)
    schedule_id = created["id"]
    assert created["kind"] == "scrape"
    assert created["cron"] == "0 9 * * *"
    assert created["timezone"] == "UTC"
    assert created["watched_fields"] == ["title"]
    assert created["next_run_at"]
    assert created["last_run_at"] is None

    listed = client.get("/v1/schedules", headers=auth_header(token))
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == schedule_id

    fetched = client.get(f"/v1/schedules/{schedule_id}", headers=auth_header(token))
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Daily homepage"

    updated = client.patch(
        f"/v1/schedules/{schedule_id}",
        headers=auth_header(token),
        json={"name": "Hourly", "cron": "15 * * * *", "enabled": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Hourly"
    assert updated.json()["cron"] == "15 * * * *"
    assert updated.json()["enabled"] is False

    other = _signup(client, email="other@example.com", org="Other")
    assert client.get(f"/v1/schedules/{schedule_id}", headers=auth_header(other)).status_code == 404
    assert (
        client.patch(
            f"/v1/schedules/{schedule_id}",
            headers=auth_header(other),
            json={"name": "Stolen"},
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/v1/schedules/{schedule_id}", headers=auth_header(other)).status_code == 404
    )
    assert (
        client.post(f"/v1/schedules/{schedule_id}/run", headers=auth_header(other)).status_code
        == 404
    )

    deleted = client.delete(f"/v1/schedules/{schedule_id}", headers=auth_header(token))
    assert deleted.status_code == 204
    assert client.get(f"/v1/schedules/{schedule_id}", headers=auth_header(token)).status_code == 404


def test_schedule_validation_rejects_bad_cron_timezone_fields_and_templates(
    client: TestClient,
) -> None:
    token = _signup(client)
    cases = [
        {"cron": "* * * *"},
        {"cron": "x * * * *"},
        {"timezone": "Mars/Olympus_Mons"},
        {"watched_fields": ["a..b"]},
        {"watched_fields": ["title", "title"]},
        {"template": {"url": PUBLIC_URL, "webhook_url": WEBHOOK_URL}},
        {
            "kind": "automation",
            "template": {
                "url": PUBLIC_URL,
                "steps": [{"action": "goto", "url": PUBLIC_URL}],
                "secrets": {"token": "hunter2"},
            },
        },
        {
            "kind": "automation",
            "template": {
                "url": PUBLIC_URL,
                "steps": [{"action": "goto", "url": PUBLIC_URL}],
                "webhook_url": WEBHOOK_URL,
            },
        },
    ]
    for overrides in cases:
        response = client.post(
            "/v1/schedules", headers=auth_header(token), json=_schedule_payload(**overrides)
        )
        assert response.status_code == 422, (overrides, response.text)


def test_run_now_creates_a_scheduled_job_and_history(
    client: TestClient,
    integration_settings: Settings,
    dispatcher: RecordingDispatcher,
) -> None:
    token = _signup(client)
    created = _create_schedule(client, token)
    schedule_id = uuid.UUID(created["id"])

    response = client.post(f"/v1/schedules/{schedule_id}/run", headers=auth_header(token))
    assert response.status_code == 200, response.text
    body = response.json()
    job_id = uuid.UUID(body["job"]["id"])
    assert body["job"]["status"] == "queued"
    assert body["run"]["job_id"] == str(job_id)
    assert body["run"]["trigger"] == "manual"
    assert body["run"]["status"] == "queued"
    assert dispatcher.enqueued == [job_id]

    row = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT org_id, schedule_id, idempotency_key FROM jobs WHERE id = $1",
            job_id,
        )
    )
    assert row is not None
    assert row["schedule_id"] == schedule_id
    assert str(row["idempotency_key"]).startswith("manual:")

    runs = client.get(f"/v1/schedules/{schedule_id}/runs", headers=auth_header(token))
    assert runs.status_code == 200, runs.text
    assert runs.json()["total"] == 1
    assert runs.json()["items"][0]["job_id"] == str(job_id)

    history = client.get(f"/v1/schedules/{schedule_id}/history", headers=auth_header(token))
    assert history.status_code == 200
    assert history.json()["total"] == 1

    refreshed = client.get(f"/v1/schedules/{schedule_id}", headers=auth_header(token))
    assert refreshed.json()["last_job_id"] == str(job_id)
    assert refreshed.json()["last_run_at"] is not None


def test_due_schedule_dispatches_exactly_once(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    token = _signup(client)
    created = _create_schedule(client, token)
    schedule_id = uuid.UUID(created["id"])
    asyncio.run(_due(integration_settings, schedule_id))

    dispatched: list[uuid.UUID] = []
    first = _dispatch(integration_settings, dispatched=dispatched)
    assert first == {"dispatched": 1, "skipped": 0, "due": 1}
    assert len(dispatched) == 1

    second = _dispatch(integration_settings, dispatched=dispatched)
    assert second == {"dispatched": 0, "skipped": 0, "due": 0}
    assert len(dispatched) == 1

    row = asyncio.run(
        _fetchrow(
            integration_settings,
            """
            SELECT j.id, j.schedule_id, r.run_key, r.trigger
            FROM jobs j JOIN schedule_runs r ON r.job_id = j.id
            WHERE j.schedule_id = $1
            """,
            schedule_id,
        )
    )
    assert row is not None
    assert row["schedule_id"] == schedule_id
    assert str(row["run_key"]).startswith(f"cron:{schedule_id}:")
    assert row["trigger"] == "cron"

    runs = client.get(f"/v1/schedules/{schedule_id}/runs", headers=auth_header(token))
    assert runs.json()["total"] == 1


def test_change_detection_stores_baseline_then_reports_changes(
    client: TestClient,
    integration_settings: Settings,
    dispatcher: RecordingDispatcher,
) -> None:
    token = _signup(client)
    created = _create_schedule(client, token, watched_fields=["title", "missing"])
    schedule_id = uuid.UUID(created["id"])
    org_id = uuid.UUID(
        str(
            asyncio.run(
                _fetchval(
                    integration_settings,
                    "SELECT org_id FROM schedules WHERE id = $1",
                    schedule_id,
                )
            )
        )
    )

    first = client.post(f"/v1/schedules/{schedule_id}/run", headers=auth_header(token))
    assert first.status_code == 200, first.text
    first_job = uuid.UUID(first.json()["job"]["id"])
    asyncio.run(_finish_job(integration_settings, first_job, result={"title": "One"}))
    _process(integration_settings, first_job)
    _release_slot(integration_settings, org_id, first_job)

    first_run = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT status, values, changes FROM schedule_runs WHERE job_id = $1",
            first_job,
        )
    )
    assert first_run is not None
    assert first_run["status"] == "succeeded"
    assert _as_json(first_run["values"]) == {"title": "One", "missing": None}
    assert _as_json(first_run["changes"]) == []

    second = client.post(f"/v1/schedules/{schedule_id}/run", headers=auth_header(token))
    assert second.status_code == 200, second.text
    second_job = uuid.UUID(second.json()["job"]["id"])
    asyncio.run(
        _finish_job(
            integration_settings,
            second_job,
            result={"title": "Two", "missing": "now present"},
        )
    )
    _process(integration_settings, second_job)

    second_run = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT values, changes FROM schedule_runs WHERE job_id = $1",
            second_job,
        )
    )
    assert second_run is not None
    assert _as_json(second_run["values"]) == {"title": "Two", "missing": "now present"}
    changes = {item["field"]: item for item in _as_json(second_run["changes"])}
    assert changes["title"]["type"] == "changed"
    assert changes["title"]["previous"] == "One"
    assert changes["title"]["current"] == "Two"
    assert changes["missing"]["type"] == "appeared"
    assert changes["missing"]["current"] == "now present"


def test_change_notifications_respect_notify_on_change(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    token = _signup(client)
    endpoint = client.post(
        "/v1/webhooks",
        headers=auth_header(token),
        json={
            "url": WEBHOOK_URL,
            "events": ["schedule.changed"],
            "description": "change feed",
        },
    )
    assert endpoint.status_code == 201, endpoint.text
    created = _create_schedule(
        client,
        token,
        watched_fields=["title"],
        notify_on_change=False,
    )
    schedule_id = uuid.UUID(created["id"])
    org_id = uuid.UUID(
        str(
            asyncio.run(
                _fetchval(
                    integration_settings,
                    "SELECT org_id FROM schedules WHERE id = $1",
                    schedule_id,
                )
            )
        )
    )

    def record(title: str) -> uuid.UUID:
        response = client.post(f"/v1/schedules/{schedule_id}/run", headers=auth_header(token))
        assert response.status_code == 200, response.text
        job_id = uuid.UUID(response.json()["job"]["id"])
        asyncio.run(_finish_job(integration_settings, job_id, result={"title": title}))
        _process(integration_settings, job_id)
        _release_slot(integration_settings, org_id, job_id)
        return job_id

    record("One")
    record("Two")
    assert (
        asyncio.run(
            _fetchval(
                integration_settings,
                "SELECT count(*) FROM webhook_deliveries WHERE event_type = 'schedule.changed'",
            )
        )
        == 0
    )

    enabled = client.patch(
        f"/v1/schedules/{schedule_id}",
        headers=auth_header(token),
        json={"notify_on_change": True},
    )
    assert enabled.status_code == 200, enabled.text
    third = record("Three")
    row = asyncio.run(
        _fetchrow(
            integration_settings,
            """
            SELECT payload FROM webhook_deliveries
            WHERE event_type = 'schedule.changed' AND payload->'data'->>'job_id' = $1
            """,
            str(third),
        )
    )
    assert row is not None
    payload = _as_json(row["payload"])
    assert payload["type"] == "schedule.changed"
    assert payload["data"]["schedule_id"] == str(schedule_id)
    assert payload["data"]["changes"][0]["field"] == "title"
    assert payload["data"]["changes"][0]["type"] == "changed"


def test_failed_scheduled_job_records_error_without_changes(
    client: TestClient,
    integration_settings: Settings,
    dispatcher: RecordingDispatcher,
) -> None:
    token = _signup(client)
    created = _create_schedule(client, token)
    schedule_id = uuid.UUID(created["id"])

    response = client.post(f"/v1/schedules/{schedule_id}/run", headers=auth_header(token))
    assert response.status_code == 200, response.text
    job_id = uuid.UUID(response.json()["job"]["id"])
    asyncio.run(
        _execute(
            integration_settings,
            """
            UPDATE jobs SET status = 'failed', finished_at = $2,
                   error_code = 'TARGET_ERROR', error_message = 'boom'
            WHERE id = $1
            """,
            job_id,
            datetime.now(UTC),
        )
    )
    _process(integration_settings, job_id)

    run = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT status, values, changes, error FROM schedule_runs WHERE job_id = $1",
            job_id,
        )
    )
    assert run is not None
    assert run["status"] == "failed"
    assert run["values"] is None
    assert run["changes"] is None

    schedule = client.get(f"/v1/schedules/{schedule_id}", headers=auth_header(token)).json()
    assert schedule["last_error"] == "boom"
    assert (
        asyncio.run(
            _fetchval(
                integration_settings,
                "SELECT count(*) FROM schedule_runs WHERE schedule_id = $1",
                schedule_id,
            )
        )
        == 1
    )
