from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import apps.worker.tasks.jobs as job_tasks
import pytest
import structlog
from apps.api.main import create_app
from fastapi.testclient import TestClient
from packages.core.logging import configure_logging, get_logger
from packages.core.observability import (
    record_job_completion,
    record_quota_rejection,
    record_rate_limit_hit,
    record_webhook_delivery,
)
from packages.core.settings import Settings


def test_json_logs_include_request_and_job_ids(
    settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    structlog.reset_defaults()
    configure_logging(settings)
    structlog.contextvars.bind_contextvars(request_id="req-123", job_id="job-456")

    get_logger("scrapeflow.test").info("worker.step", status="ok")

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    payload = json.loads(lines[-1])
    assert payload["event"] == "worker.step"
    assert payload["request_id"] == "req-123"
    assert payload["job_id"] == "job-456"
    assert payload["level"] == "info"
    assert "timestamp" in payload
    structlog.contextvars.clear_contextvars()


def test_access_log_binds_request_id(
    settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    structlog.reset_defaults()
    app_client = TestClient(create_app(settings, probes=[]))
    with app_client as client:
        response = client.get("/health", headers={"X-Request-ID": "req-abc"})

    assert response.headers["X-Request-ID"] == "req-abc"
    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    access = [record for record in records if record.get("event") == "request"]
    assert access, records
    assert access[-1]["request_id"] == "req-abc"
    assert access[-1]["path"] == "/health"
    assert access[-1]["status"] == 200


def test_invalid_request_id_is_replaced(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings, probes=[])) as client:
        response = client.get("/health", headers={"X-Request-ID": "bad id with spaces"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad id with spaces"


def test_run_job_binds_job_id_for_its_log_scope(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []

    async def fake_execute(
        job_id: uuid.UUID,
        worker_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        captured.append(dict(structlog.contextvars.get_contextvars()))
        return {"job_id": str(job_id), "status": "succeeded"}

    async def fake_terminal(*args: Any, **kwargs: Any) -> None:
        captured.append(dict(structlog.contextvars.get_contextvars()))

    monkeypatch.setattr(job_tasks, "_execute_job", fake_execute)
    monkeypatch.setattr(job_tasks, "process_terminal_job", fake_terminal)

    job_id = uuid.uuid4()
    result = asyncio.run(job_tasks._run_job(job_id, "worker:1", settings=settings))

    assert result["job_id"] == str(job_id)
    assert captured[0]["job_id"] == str(job_id)
    assert captured[1]["job_id"] == str(job_id)
    assert "job_id" not in structlog.contextvars.get_contextvars()


def test_sentry_is_initialised_without_pii(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import apps.api.main as app_module

    captured: dict[str, object] = {}

    def fake_init(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(app_module.sentry_sdk, "init", fake_init)
    create_app(
        settings.model_copy(update={"sentry_dsn": "https://public@example.com/1"}),
        probes=[],
    )

    assert captured["environment"] == "test"
    assert captured["send_default_pii"] is False
    assert captured["traces_sample_rate"] == 0.0
    assert captured["release"] == "scrapeflow@0.1.0"


def test_metric_helpers_record_expected_labels() -> None:
    from prometheus_client import REGISTRY

    record_job_completion(
        kind="scrape",
        status="failed",
        duration_seconds=0.75,
        error_code="TIMEOUT",
    )
    record_webhook_delivery(event="job.failed", result="retrying")
    record_quota_rejection(reason="concurrency")
    record_rate_limit_hit(scope="ip")

    def value(name: str, labels: dict[str, str]) -> float:
        return REGISTRY.get_sample_value(name, labels) or 0.0

    assert value("scrapeflow_jobs_total", {"kind": "scrape", "status": "failed"}) >= 1
    assert value("scrapeflow_job_failures_total", {"kind": "scrape", "code": "TIMEOUT"}) >= 1
    assert (
        value("scrapeflow_webhook_deliveries_total", {"event": "job.failed", "result": "retrying"})
        >= 1
    )
    assert value("scrapeflow_quota_rejections_total", {"reason": "concurrency"}) >= 1
    assert value("scrapeflow_rate_limit_hits_total", {"scope": "ip"}) >= 1
