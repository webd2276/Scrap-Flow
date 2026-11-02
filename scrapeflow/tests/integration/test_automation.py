from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import asyncpg
import pytest
from apps.worker import job_store
from apps.worker import secrets as worker_secrets
from apps.worker.automate import AutomationOutcome
from apps.worker.tasks import jobs as worker_jobs
from apps.worker.tasks.jobs import _run_job
from fastapi.testclient import TestClient
from packages.core.errors import AppError, ErrorCode
from packages.core.settings import Settings
from tests.integration.conftest import RecordingDispatcher, auth_header, signup_payload

PUBLIC_URL = "https://93.184.216.34/"


def _signup(client: TestClient, email: str = "owner@example.com") -> str:
    response = client.post("/v1/auth/signup", json=signup_payload(email=email, org="Acme"))
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _automation_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": PUBLIC_URL,
        "steps": [
            {"action": "type", "selector": "#email", "text": "{{email}}"},
            {"action": "click", "selector": "#submit"},
            {"action": "extract", "name": "message", "selector": "#message"},
        ],
        "secrets": {"email": "user@example.com"},
    }
    payload.update(overrides)
    return payload


def test_submit_automation_creates_durable_job_without_secret_values(
    client: TestClient,
    dispatcher: RecordingDispatcher,
    integration_settings: Settings,
) -> None:
    token = _signup(client)
    response = client.post("/v1/automate", headers=auth_header(token), json=_automation_payload())
    assert response.status_code == 202, response.text
    job = response.json()["job"]
    job_id = uuid.UUID(job["id"])
    assert job["kind"] == "automation"
    assert job["status"] == "queued"
    assert dispatcher.enqueued == [job_id]
    assert "user@example.com" not in json.dumps(job)

    payload = asyncio.run(_job_payload(integration_settings, job_id))
    assert "user@example.com" not in json.dumps(payload)
    assert payload["steps"][0]["text"] == "{{email}}"

    staged = worker_secrets.load_secrets(integration_settings, job_id)
    assert staged == {"email": "user@example.com"}

    worker_secrets.delete_secrets(integration_settings, job_id)
    assert worker_secrets.load_secrets(integration_settings, job_id) == {}


def test_idempotent_replay_does_not_create_a_second_job(
    client: TestClient, dispatcher: RecordingDispatcher
) -> None:
    token = _signup(client)
    headers = auth_header(token) | {"Idempotency-Key": "automation-1"}
    first = client.post("/v1/automate", headers=headers, json=_automation_payload())
    second = client.post(
        "/v1/automate",
        headers=headers,
        json=_automation_payload(secrets={"email": "other@example.com"}),
    )
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.headers["Idempotent-Replay"] == "true"
    assert first.json()["job"]["id"] == second.json()["job"]["id"]
    assert len(dispatcher.enqueued) == 1


def test_automation_ssrf_and_validation(
    client: TestClient, dispatcher: RecordingDispatcher
) -> None:
    token = _signup(client)
    blocked = client.post(
        "/v1/automate",
        headers=auth_header(token),
        json=_automation_payload(url="http://127.0.0.1/"),
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "BLOCKED_URL"

    blocked_goto = client.post(
        "/v1/automate",
        headers=auth_header(token),
        json=_automation_payload(
            steps=[
                {"action": "goto", "url": "http://169.254.169.254/latest/meta-data/"},
                {"action": "click", "selector": "#x"},
            ]
        ),
    )
    assert blocked_goto.status_code == 422
    assert blocked_goto.json()["error"]["code"] == "BLOCKED_URL"

    unknown_action = client.post(
        "/v1/automate",
        headers=auth_header(token),
        json=_automation_payload(steps=[{"action": "explode"}]),
    )
    assert unknown_action.status_code == 422
    assert dispatcher.enqueued == []


def test_automation_scope_is_separate_from_scrape(client: TestClient) -> None:
    token = _signup(client)
    scraper = client.post(
        "/v1/keys",
        headers=auth_header(token),
        json={"name": "scraper", "scopes": ["scrape:write"]},
    ).json()["key"]
    automator = client.post(
        "/v1/keys",
        headers=auth_header(token),
        json={"name": "automator", "scopes": ["automation:write"]},
    ).json()["key"]

    denied = client.post(
        "/v1/automate",
        headers={"X-API-Key": scraper},
        json=_automation_payload(),
    )
    assert denied.status_code == 403

    allowed = client.post(
        "/v1/automate",
        headers={"X-API-Key": automator},
        json=_automation_payload(),
    )
    assert allowed.status_code == 202


def test_worker_marks_automation_success_and_failure(
    client: TestClient,
    integration_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _signup(client)
    success_id = uuid.UUID(
        client.post("/v1/automate", headers=auth_header(token), json=_automation_payload()).json()[
            "job"
        ]["id"]
    )
    failure_id = uuid.UUID(
        client.post(
            "/v1/automate",
            headers=auth_header(token),
            json=_automation_payload(
                steps=[{"action": "click", "selector": "#missing"}],
                secrets={},
            ),
        ).json()["job"]["id"]
    )

    async def fake_success(**_kwargs: Any) -> AutomationOutcome:
        return AutomationOutcome(result={"ok": True}, artifacts=())

    async def fake_failure(**_kwargs: Any) -> AutomationOutcome:
        return AutomationOutcome(
            result={"ok": False},
            artifacts=(),
            failure=AppError(
                422,
                ErrorCode.STEP_FAILED,
                "Step 0 failed",
                details={"step": "0", "action": "click"},
            ),
        )

    monkeypatch.setattr(worker_jobs, "execute_automation", fake_success)
    success = asyncio.run(_run_isolated(success_id, integration_settings))
    assert success["status"] == "succeeded"
    job = asyncio.run(_job_row(integration_settings, success_id))
    assert job["status"] == "succeeded"
    assert job["result"] == {"ok": True}

    monkeypatch.setattr(worker_jobs, "execute_automation", fake_failure)
    failure = asyncio.run(_run_isolated(failure_id, integration_settings))
    assert failure["status"] == "failed"
    job = asyncio.run(_job_row(integration_settings, failure_id))
    assert job["status"] == "failed"
    assert job["error_code"] == "STEP_FAILED"
    assert job["result"] == {"ok": False}


async def _run_isolated(job_id: uuid.UUID, settings: Settings) -> dict[str, Any]:
    try:
        return await _run_job(job_id, "test-worker", settings=settings)
    finally:
        await job_store.dispose()


async def _job_payload(settings: Settings, job_id: uuid.UUID) -> dict[str, Any]:
    connection = await asyncpg.connect(settings.asyncpg_dsn)
    try:
        value = await connection.fetchval("SELECT payload FROM jobs WHERE id = $1", job_id)
        return json.loads(value) if isinstance(value, str) else value
    finally:
        await connection.close()


async def _job_row(settings: Settings, job_id: uuid.UUID) -> dict[str, Any]:
    connection = await asyncpg.connect(settings.asyncpg_dsn)
    try:
        row = await connection.fetchrow(
            "SELECT status, error_code, result FROM jobs WHERE id = $1", job_id
        )
        assert row is not None
        result = row["result"]
        return {
            "status": row["status"],
            "error_code": row["error_code"],
            "result": json.loads(result) if isinstance(result, str) else result,
        }
    finally:
        await connection.close()
