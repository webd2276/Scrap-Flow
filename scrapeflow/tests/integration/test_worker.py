from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from apps.api.schemas.scrape import ScrapeRequest
from apps.worker import job_store
from apps.worker.scrape import execute_scrape
from apps.worker.tasks.jobs import _run_job
from apps.worker.tasks.reaper import _reap
from packages.core.errors import AppError, ErrorCode
from packages.core.models import Job, JobKind, JobStatus
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy
from redis.asyncio import Redis
from tests.integration.conftest import signup_payload

PAGE = b"""<!doctype html>
<html><head><title>Local Page</title></head>
<body>
  <h1 id="title">Hello</h1>
  <p>Body text</p>
  <a href="/two">Two</a>
  <a class="next" href="/page2">Next</a>
</body></html>"""

PAGE2 = b"""<!doctype html>
<html><head><title>Page Two</title></head>
<body><h1 id="title">Second</h1><p>More text</p></body></html>"""


async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
        target = head.split(b" ")[1]
        body = PAGE2 if target.startswith(b"/page2") else PAGE
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + body
        )
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


@asynccontextmanager
async def _origin() -> AsyncIterator[int]:
    """Serve the fixture page on the loop that also runs the worker.

    A pytest async fixture would bind the server to the pytest loop, which is
    idle while ``asyncio.run`` executes the job, so the accept would hang.
    """
    server = await asyncio.start_server(_handler, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    try:
        yield port
    finally:
        server.close()
        await server.wait_closed()


def _as_json(value: Any) -> Any:
    """asyncpg returns jsonb as text unless a codec is registered."""
    return json.loads(value) if isinstance(value, str) else value


def _settings(integration_settings: Settings, port: int) -> Settings:
    return integration_settings.model_copy(
        update={
            "egress_allowed_ports": f"80,443,{port}",
            "job_timeout_seconds": 30,
            "job_lease_seconds": 90,
            "http_timeout_seconds": 10,
        }
    )


def _policy(port: int) -> SSRFPolicy:
    return SSRFPolicy(
        allowed_ports=frozenset({80, 443, port}),
        allowed_private_hosts=frozenset({"127.0.0.1"}),
    )


async def _connect(settings: Settings) -> asyncpg.Connection:
    return await asyncpg.connect(settings.asyncpg_dsn)


async def _create_org_and_user(client: Any) -> tuple[uuid.UUID, uuid.UUID]:
    response = client.post("/v1/auth/signup", json=signup_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    return uuid.UUID(body["org_id"]), uuid.UUID(body["user_id"])


async def _insert_job(
    settings: Settings,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    url: str,
    payload: dict[str, Any],
    status: str = "queued",
    attempts: int = 0,
    max_attempts: int = 2,
    lease_expires_at: datetime | None = None,
    started_at: datetime | None = None,
    cancel_requested_at: datetime | None = None,
) -> uuid.UUID:
    job_id = uuid.uuid4()
    connection = await _connect(settings)
    try:
        await connection.execute(
            "INSERT INTO jobs (id, org_id, created_by, kind, status, url, payload, "
            "idempotency_key, attempts, max_attempts, lease_expires_at, started_at, "
            "cancel_requested_at) VALUES ($1, $2, $3, 'scrape', $4, $5, $6::jsonb, "
            "NULL, $7, $8, $9, $10, $11)",
            job_id,
            org_id,
            user_id,
            status,
            url,
            json.dumps(payload),
            attempts,
            max_attempts,
            lease_expires_at,
            started_at,
            cancel_requested_at,
        )
    finally:
        await connection.close()
    return job_id


async def _job_row(settings: Settings, job_id: uuid.UUID) -> asyncpg.Record:
    connection = await _connect(settings)
    try:
        row = await connection.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
        assert row is not None
        return row
    finally:
        await connection.close()


async def _artifacts(settings: Settings, job_id: uuid.UUID) -> list[asyncpg.Record]:
    connection = await _connect(settings)
    try:
        return list(
            await connection.fetch(
                "SELECT * FROM artifacts WHERE job_id = $1 ORDER BY kind", job_id
            )
        )
    finally:
        await connection.close()


def test_scrape_http_job_succeeds_and_stores_artifacts(
    client: Any, integration_settings: Settings
) -> None:
    async def run() -> tuple[asyncpg.Record, list[asyncpg.Record], Settings]:
        async with _origin() as origin:
            settings = _settings(integration_settings, origin)
            try:
                org_id, user_id = await _create_org_and_user(client)
                request = ScrapeRequest(
                    url=f"http://127.0.0.1:{origin}/",
                    selectors={
                        "heading": {"css": "h1#title"},
                        "paragraph": {"css": "p"},
                    },
                    include_html=True,
                )
                job_id = await _insert_job(
                    settings,
                    org_id=org_id,
                    user_id=user_id,
                    url=request.url,
                    payload=request.model_dump(mode="json"),
                )
                result = await _run_job(
                    job_id, "test-worker", settings=settings, policy=_policy(origin)
                )
                assert result["status"] == "succeeded", result
                return (
                    await _job_row(settings, job_id),
                    await _artifacts(settings, job_id),
                    settings,
                )
            finally:
                await job_store.dispose()

    row, artifacts, settings = asyncio.run(run())
    assert row["status"] == "succeeded"
    assert row["attempts"] == 1
    assert row["duration_ms"] is not None
    result = _as_json(row["result"])
    assert result["title"] == "Local Page"
    assert "Body text" in result["text"]
    assert result["selectors"]["heading"] == "Hello"
    assert result["status_code"] == 200
    assert {artifact["kind"] for artifact in artifacts} == {"html", "result"}
    root = Path(settings.artifacts_local_dir)
    now = datetime.now(UTC)
    for artifact in artifacts:
        assert (root / artifact["storage_key"]).is_file()
        # The default org is on the free plan (1-day retention), not the
        # deployment-level 7-day fallback.
        assert now + timedelta(hours=23) < artifact["expires_at"] < now + timedelta(hours=25)


def test_pagination_collects_pages(client: Any, integration_settings: Settings) -> None:
    async def run() -> asyncpg.Record:
        async with _origin() as origin:
            settings = _settings(integration_settings, origin)
            try:
                org_id, user_id = await _create_org_and_user(client)
                request = ScrapeRequest(
                    url=f"http://127.0.0.1:{origin}/",
                    extract={"title": True, "text": False},
                    pagination={"next_selector": {"css": "a.next"}, "max_pages": 3},
                )
                job_id = await _insert_job(
                    settings,
                    org_id=org_id,
                    user_id=user_id,
                    url=request.url,
                    payload=request.model_dump(mode="json"),
                )
                await _run_job(job_id, "test-worker", settings=settings, policy=_policy(origin))
                return await _job_row(settings, job_id)
            finally:
                await job_store.dispose()

    row = asyncio.run(run())
    assert row["status"] == "succeeded"
    assert [page["title"] for page in _as_json(row["result"])["pages"]] == [
        "Local Page",
        "Page Two",
    ]


def test_cancelled_job_never_runs(client: Any, integration_settings: Settings) -> None:
    async def run() -> asyncpg.Record:
        async with _origin() as origin:
            settings = _settings(integration_settings, origin)
            try:
                org_id, user_id = await _create_org_and_user(client)
                request = ScrapeRequest(url=f"http://127.0.0.1:{origin}/")
                job_id = await _insert_job(
                    settings,
                    org_id=org_id,
                    user_id=user_id,
                    url=request.url,
                    payload=request.model_dump(mode="json"),
                    cancel_requested_at=datetime.now(UTC),
                )
                await _run_job(job_id, "test-worker", settings=settings, policy=_policy(origin))
                return await _job_row(settings, job_id)
            finally:
                await job_store.dispose()

    row = asyncio.run(run())
    assert row["status"] == "cancelled"
    assert row["result"] is None


def test_deadline_is_enforced(client: Any, integration_settings: Settings) -> None:
    async def run() -> None:
        async with _origin() as origin:
            settings = _settings(integration_settings, origin)
            try:
                org_id, user_id = await _create_org_and_user(client)
                request = ScrapeRequest(url=f"http://127.0.0.1:{origin}/")
                job_id = await _insert_job(
                    settings,
                    org_id=org_id,
                    user_id=user_id,
                    url=request.url,
                    payload=request.model_dump(mode="json"),
                )
                row = await _job_row(settings, job_id)
                job = Job(
                    id=row["id"],
                    org_id=row["org_id"],
                    created_by=row["created_by"],
                    kind=JobKind(row["kind"]),
                    status=JobStatus(row["status"]),
                    url=row["url"],
                    payload=_as_json(row["payload"]),
                    attempts=row["attempts"],
                    max_attempts=row["max_attempts"],
                )
                with pytest.raises(AppError) as exc:
                    await execute_scrape(
                        job=job,
                        settings=settings,
                        sessionmaker=job_store.sessionmaker(settings),
                        deadline=time.monotonic() - 1,
                        policy=_policy(origin),
                    )
                assert exc.value.code == ErrorCode.TIMEOUT
            finally:
                await job_store.dispose()

    asyncio.run(run())


def test_reaper_requeues_and_fails_lost_jobs(client: Any, integration_settings: Settings) -> None:
    async def run() -> tuple[asyncpg.Record, asyncpg.Record, list[uuid.UUID]]:
        async with _origin() as origin:
            settings = _settings(integration_settings, origin)
            try:
                org_id, user_id = await _create_org_and_user(client)
                request = ScrapeRequest(url=f"http://127.0.0.1:{origin}/")
                past = datetime.now(UTC) - timedelta(minutes=5)
                payload = request.model_dump(mode="json")
                requeue_id = await _insert_job(
                    settings,
                    org_id=org_id,
                    user_id=user_id,
                    url=request.url,
                    payload=payload,
                    status="running",
                    attempts=1,
                    lease_expires_at=past,
                    started_at=past,
                )
                lost_id = await _insert_job(
                    settings,
                    org_id=org_id,
                    user_id=user_id,
                    url=request.url,
                    payload=payload,
                    status="running",
                    attempts=2,
                    lease_expires_at=past,
                    started_at=past,
                )
                dispatched: list[uuid.UUID] = []
                summary = await _reap(settings=settings, dispatch_job=dispatched.append)
                assert summary["requeued"] == 1
                assert summary["failed"] == 1
                return (
                    await _job_row(settings, requeue_id),
                    await _job_row(settings, lost_id),
                    dispatched,
                )
            finally:
                await job_store.dispose()

    requeued, lost, dispatched = asyncio.run(run())
    assert requeued["status"] == "queued"
    assert requeued["worker_id"] is None
    assert lost["status"] == "failed"
    assert lost["error_code"] == "WORKER_LOST"
    assert requeued["id"] in dispatched


def test_reaper_reuses_engine_across_event_loops(integration_settings: Settings) -> None:
    """Celery runs every task in a fresh event loop.

    The worker engine must not hand a pooled asyncpg connection from a previous
    task loop to the next task. This reproduced a RuntimeError in the live
    compose stack before the worker switched to NullPool.
    """

    async def clear_lock() -> None:
        redis = Redis.from_url(integration_settings.redis_url, decode_responses=True)
        try:
            await redis.delete("sf:reaper:lock")
        finally:
            await redis.aclose()

    async def run_once() -> dict[str, int]:
        return await _reap(settings=integration_settings)

    try:
        first = asyncio.run(run_once())
        asyncio.run(clear_lock())
        second = asyncio.run(run_once())
    finally:
        asyncio.run(job_store.dispose())

    assert first["requeued"] == 0
    assert second["requeued"] == 0


def test_browser_path_requires_validated_proxy(integration_settings: Settings) -> None:
    settings = integration_settings.model_copy(
        update={"selenium_remote_url": "http://grid:4444", "egress_proxy_url": None}
    )

    async def run() -> None:
        try:
            job = Job(
                id=uuid.uuid4(),
                org_id=uuid.uuid4(),
                kind=JobKind.SCRAPE,
                status=JobStatus.RUNNING,
                url="https://example.com/",
                payload=ScrapeRequest(url="https://example.com/", render_js=True).model_dump(
                    mode="json"
                ),
                attempts=1,
                max_attempts=2,
            )
            with pytest.raises(AppError) as exc:
                await execute_scrape(
                    job=job,
                    settings=settings,
                    sessionmaker=job_store.sessionmaker(settings),
                    deadline=time.monotonic() + 10,
                )
            assert exc.value.code == ErrorCode.SERVICE_UNAVAILABLE
        finally:
            await job_store.dispose()

    asyncio.run(run())


@pytest.mark.skip(reason="requires Chrome/Grid; unit tests cover the injected driver")
def test_browser_runner_requires_real_chrome() -> None:
    pass
