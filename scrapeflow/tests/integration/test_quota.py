from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest
from apps.worker import job_store
from apps.worker.scrape import ScrapeOutcome
from apps.worker.tasks import jobs as worker_jobs
from apps.worker.tasks.jobs import _run_job
from apps.worker.tasks.reconcile import _reconcile
from apps.worker.tasks.retention import _purge
from fastapi.testclient import TestClient
from packages.core.artifacts import ArtifactStore
from packages.core.errors import AppError, ErrorCode
from packages.core.quota import QuotaStore, period_key
from packages.core.settings import Settings
from redis.asyncio import Redis
from tests.integration.conftest import RecordingDispatcher, auth_header, signup_payload

PUBLIC_URL = "https://93.184.216.34/"


def _signup(client: TestClient, email: str = "owner@example.com") -> str:
    response = client.post("/v1/auth/signup", json=signup_payload(email=email, org="Acme"))
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _submit(client: TestClient, token: str, **overrides: Any) -> Any:
    return client.post(
        "/v1/scrape",
        headers=auth_header(token),
        json={"url": PUBLIC_URL, **overrides},
    )


async def _fetchval(settings: Settings, query: str, *args: object) -> object:
    connection = await asyncpg.connect(settings.asyncpg_dsn)
    try:
        return await connection.fetchval(query, *args)
    finally:
        await connection.close()


async def _fetchrow(settings: Settings, query: str, *args: object) -> asyncpg.Record | None:
    connection = await asyncpg.connect(settings.asyncpg_dsn)
    try:
        return await connection.fetchrow(query, *args)
    finally:
        await connection.close()


async def _redis_used(settings: Settings, org_id: uuid.UUID) -> int:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        return await QuotaStore(redis).current(org_id, period=period_key())
    finally:
        await redis.aclose()


async def _redis_set_used(settings: Settings, org_id: uuid.UUID, value: int) -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.set(QuotaStore.quota_key(org_id, period_key()), str(value))
    finally:
        await redis.aclose()


async def _redis_active(settings: Settings, org_id: uuid.UUID) -> int:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        return await QuotaStore(redis).active_slots(org_id)
    finally:
        await redis.aclose()


async def _run_isolated(job_id: uuid.UUID, settings: Settings) -> dict[str, Any]:
    try:
        return await _run_job(job_id, "test-worker", settings=settings)
    finally:
        await job_store.dispose()


def test_acceptance_reserves_credits_and_returns_headers(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    token = _signup(client)
    response = _submit(client, token)
    assert response.status_code == 202, response.text
    assert response.headers["x-quota-limit"] == "100"
    assert response.headers["x-quota-remaining"] == "99"
    assert int(response.headers["x-quota-reset"]) > 0
    assert response.headers["x-concurrency-limit"] == "1"
    assert response.headers["x-concurrency-remaining"] == "0"

    job_id = uuid.UUID(response.json()["job"]["id"])
    org_id = uuid.UUID(
        str(
            asyncio.run(
                _fetchval(integration_settings, "SELECT org_id FROM jobs WHERE id = $1", job_id)
            )
        )
    )
    row = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT credits, status, period FROM usage_ledger WHERE job_id = $1",
            job_id,
        )
    )
    assert row is not None
    assert row["credits"] == 1
    assert row["status"] == "reserved"
    assert row["period"] == period_key()
    assert asyncio.run(_redis_used(integration_settings, org_id)) == 1
    assert asyncio.run(_redis_active(integration_settings, org_id)) == 1

    usage = client.get("/v1/billing/usage", headers=auth_header(token))
    assert usage.status_code == 200, usage.text
    assert usage.json()["plan"] == "free"
    assert usage.json()["used"] == 1
    assert usage.json()["remaining"] == 99


def test_queued_cancel_releases_credits_and_slot(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    token = _signup(client)
    job_id = uuid.UUID(_submit(client, token).json()["job"]["id"])
    org_id = uuid.UUID(
        str(
            asyncio.run(
                _fetchval(integration_settings, "SELECT org_id FROM jobs WHERE id = $1", job_id)
            )
        )
    )

    cancelled = client.post(f"/v1/jobs/{job_id}/cancel", headers=auth_header(token))
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["job"]["status"] == "cancelled"

    row = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT status, reason FROM usage_ledger WHERE job_id = $1",
            job_id,
        )
    )
    assert row is not None
    assert row["status"] == "released"
    assert row["reason"] == "job_never_started"
    assert asyncio.run(_redis_used(integration_settings, org_id)) == 0
    assert asyncio.run(_redis_active(integration_settings, org_id)) == 0


def test_exhaustion_returns_402_with_headers(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    token = _signup(client)
    org_id = uuid.UUID(
        str(asyncio.run(_fetchval(integration_settings, "SELECT id FROM organizations LIMIT 1")))
    )
    asyncio.run(_redis_set_used(integration_settings, org_id, 100))

    response = _submit(client, token)
    assert response.status_code == 402, response.text
    body = response.json()
    assert body["error"]["code"] == "QUOTA_EXCEEDED"
    assert response.headers["x-quota-limit"] == "100"
    assert response.headers["x-quota-remaining"] == "0"
    assert int(response.headers["retry-after"]) > 0
    assert asyncio.run(_redis_used(integration_settings, org_id)) == 100
    assert asyncio.run(_redis_active(integration_settings, org_id)) == 0
    assert asyncio.run(_fetchval(integration_settings, "SELECT count(*) FROM jobs")) == 0


def test_concurrency_limit_is_429_and_released_by_cancel(
    client: TestClient,
    dispatcher: RecordingDispatcher,
) -> None:
    token = _signup(client)
    first = _submit(client, token)
    assert first.status_code == 202
    second = _submit(client, token)
    assert second.status_code == 429, second.text
    assert second.json()["error"]["code"] == "CONCURRENCY_LIMIT"
    assert second.headers["x-concurrency-limit"] == "1"
    assert second.headers["x-concurrency-remaining"] == "0"
    assert int(second.headers["retry-after"]) >= 1
    assert len(dispatcher.enqueued) == 1

    job_id = first.json()["job"]["id"]
    assert client.post(f"/v1/jobs/{job_id}/cancel", headers=auth_header(token)).status_code == 200
    third = _submit(client, token)
    assert third.status_code == 202, third.text
    assert len(dispatcher.enqueued) == 2


def test_plan_page_and_step_limits_return_402(client: TestClient) -> None:
    token = _signup(client)
    pages = _submit(
        client,
        token,
        pagination={"next_selector": {"css": "a.next"}, "max_pages": 6},
    )
    assert pages.status_code == 402, pages.text
    assert pages.json()["error"]["code"] == "QUOTA_EXCEEDED"
    assert "5 pages" in pages.json()["error"]["message"]

    steps = client.post(
        "/v1/automate",
        headers=auth_header(token),
        json={
            "url": PUBLIC_URL,
            "steps": [{"action": "click", "selector": f"#x{index}"} for index in range(11)],
        },
    )
    assert steps.status_code == 402, steps.text
    assert "10 steps" in steps.json()["error"]["message"]


def test_successful_worker_run_commits_and_failed_run_after_start_commits(
    client: TestClient,
    integration_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _signup(client)
    job_id = uuid.UUID(_submit(client, token).json()["job"]["id"])
    org_id = uuid.UUID(
        str(
            asyncio.run(
                _fetchval(integration_settings, "SELECT org_id FROM jobs WHERE id = $1", job_id)
            )
        )
    )

    async def fake_scrape(**_kwargs: Any) -> ScrapeOutcome:
        return ScrapeOutcome(result={"ok": True}, artifacts=())

    monkeypatch.setattr(worker_jobs, "execute_scrape", fake_scrape)
    assert asyncio.run(_run_isolated(job_id, integration_settings))["status"] == "succeeded"

    row = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT status, reason FROM usage_ledger WHERE job_id = $1",
            job_id,
        )
    )
    assert row is not None
    assert row["status"] == "committed"
    assert row["reason"] == "job_succeeded"
    assert asyncio.run(_redis_used(integration_settings, org_id)) == 1
    assert asyncio.run(_redis_active(integration_settings, org_id)) == 0

    failure_id = uuid.UUID(_submit(client, token).json()["job"]["id"])

    async def fake_failure(**_kwargs: Any) -> ScrapeOutcome:
        raise AppError(502, ErrorCode.UPSTREAM_ERROR, "upstream failed")

    monkeypatch.setattr(worker_jobs, "execute_scrape", fake_failure)
    assert asyncio.run(_run_isolated(failure_id, integration_settings))["status"] == "failed"

    failed_row = asyncio.run(
        _fetchrow(
            integration_settings,
            "SELECT status, reason FROM usage_ledger WHERE job_id = $1",
            failure_id,
        )
    )
    assert failed_row is not None
    assert failed_row["status"] == "committed"
    assert failed_row["reason"] == "job_started"
    assert asyncio.run(_redis_used(integration_settings, org_id)) == 2


def test_reconcile_repairs_a_cold_redis_counter(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    token = _signup(client)
    job_id = uuid.UUID(_submit(client, token).json()["job"]["id"])
    org_id = uuid.UUID(
        str(
            asyncio.run(
                _fetchval(integration_settings, "SELECT org_id FROM jobs WHERE id = $1", job_id)
            )
        )
    )
    asyncio.run(_redis_set_used(integration_settings, org_id, 0))

    try:
        result = asyncio.run(_reconcile(settings=integration_settings, org_ids=[org_id]))
    finally:
        asyncio.run(job_store.dispose())

    assert result["organizations"] == 1
    assert asyncio.run(_redis_used(integration_settings, org_id)) == 1
    assert asyncio.run(_redis_active(integration_settings, org_id)) == 1


def test_retention_purges_expired_artifacts(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    token = _signup(client)
    job_id = uuid.UUID(_submit(client, token).json()["job"]["id"])
    org_id = uuid.UUID(
        str(
            asyncio.run(
                _fetchval(integration_settings, "SELECT org_id FROM jobs WHERE id = $1", job_id)
            )
        )
    )
    store = ArtifactStore(integration_settings)
    stored = store.put(
        org_id=org_id,
        job_id=job_id,
        filename="old.txt",
        content_type="text/plain",
        data=b"old",
    )
    artifact_id = uuid.uuid4()

    async def insert() -> None:
        connection = await asyncpg.connect(integration_settings.asyncpg_dsn)
        try:
            await connection.execute(
                "INSERT INTO artifacts (id, org_id, job_id, kind, filename, content_type, "
                "size_bytes, sha256, storage_key, expires_at) "
                "VALUES ($1, $2, $3, 'result', 'old.txt', 'text/plain', $4, $5, $6, $7)",
                artifact_id,
                org_id,
                job_id,
                stored.size_bytes,
                stored.sha256,
                stored.storage_key,
                datetime.now(UTC) - timedelta(minutes=1),
            )
        finally:
            await connection.close()

    asyncio.run(insert())
    try:
        result = asyncio.run(_purge(settings=integration_settings))
    finally:
        asyncio.run(job_store.dispose())

    assert result == {"deleted": 1, "failed": 0}
    assert (
        asyncio.run(
            _fetchval(
                integration_settings, "SELECT count(*) FROM artifacts WHERE id = $1", artifact_id
            )
        )
        == 0
    )
    assert not (store.local_root / stored.storage_key).exists()
