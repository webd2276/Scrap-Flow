from __future__ import annotations

from pathlib import Path

import pytest
from apps.api.main import create_app
from apps.api.routers import metrics as metrics_router
from fastapi.testclient import TestClient
from packages.core.observability import (
    ACTIVE_BROWSER_SESSIONS,
    DB_LATENCY_SECONDS,
    HTTP_REQUESTS_TOTAL,
    JOB_DURATION_SECONDS,
    JOBS_TOTAL,
    QUEUE_DEPTH,
    REDIS_LATENCY_SECONDS,
    WEBHOOK_PENDING,
    record_job_completion,
    record_quota_rejection,
    record_rate_limit_hit,
    record_webhook_delivery,
    start_worker_metrics_server,
)
from packages.core.settings import Settings
from pydantic import SecretStr

SERIES = (
    "scrapeflow_http_requests_total",
    "scrapeflow_http_request_duration_seconds",
    "scrapeflow_jobs_total",
    "scrapeflow_job_failures_total",
    "scrapeflow_job_duration_seconds",
    "scrapeflow_queue_depth",
    "scrapeflow_active_browser_sessions",
    "scrapeflow_webhook_deliveries_total",
    "scrapeflow_webhook_pending",
    "scrapeflow_quota_rejections_total",
    "scrapeflow_rate_limit_hits_total",
    "scrapeflow_db_latency_seconds",
    "scrapeflow_redis_latency_seconds",
)


@pytest.fixture(autouse=True)
def _sample_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    async def noop(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(metrics_router, "collect_runtime_metrics", noop)


def _client(settings: Settings) -> TestClient:
    app = create_app(settings, probes=[])
    return TestClient(app)


def test_metrics_exposes_required_series(settings: Settings) -> None:
    HTTP_REQUESTS_TOTAL.labels(method="GET", route="/health", status="200").inc()
    JOBS_TOTAL.labels(kind="scrape", status="succeeded").inc()
    JOB_DURATION_SECONDS.labels(kind="scrape", status="succeeded").observe(1.25)
    record_job_completion(
        kind="automation",
        status="failed",
        duration_seconds=0.5,
        error_code="JOB_FAILED",
    )
    QUEUE_DEPTH.labels(queue="jobs").set(3)
    ACTIVE_BROWSER_SESSIONS.set(1)
    record_webhook_delivery(event="job.completed", result="succeeded")
    WEBHOOK_PENDING.set(2)
    record_quota_rejection(reason="quota")
    record_rate_limit_hit(scope="org")
    DB_LATENCY_SECONDS.set(0.002)
    REDIS_LATENCY_SECONDS.set(0.001)

    with _client(settings) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"] == "no-store"
    for name in SERIES:
        assert f"# TYPE {name}" in response.text
    assert 'scrapeflow_job_failures_total{code="JOB_FAILED",kind="automation"} 1.0' in (
        response.text
    )


def test_http_requests_are_counted_with_route_template(
    settings: Settings,
) -> None:
    with _client(settings) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/metrics")

    assert (
        'scrapeflow_http_requests_total{method="GET",route="/health",status="200"}' in response.text
    )


def test_metrics_are_excluded_from_their_own_counters(settings: Settings) -> None:
    with _client(settings) as client:
        response = client.get("/metrics")

    assert 'route="/metrics"' not in response.text


def test_metrics_can_be_disabled(settings: Settings) -> None:
    disabled = settings.model_copy(update={"metrics_enabled": False})
    with _client(disabled) as client:
        response = client.get("/metrics")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_metrics_requires_bearer_token_when_configured(settings: Settings) -> None:
    token = "s" * 40
    guarded = settings.model_copy(update={"metrics_token": SecretStr(token)})
    with _client(guarded) as client:
        missing = client.get("/metrics")
        wrong = client.get("/metrics", headers={"Authorization": "Bearer nope"})
        basic = client.get("/metrics", headers={"Authorization": f"Basic {token}"})
        unicode = client.get(
            "/metrics",
            headers={"Authorization": "Bearer café".encode("latin-1")},
        )
        allowed = client.get("/metrics", headers={"Authorization": f"Bearer {token}"})

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert basic.status_code == 401
    assert unicode.status_code == 401
    assert allowed.status_code == 200
    assert allowed.headers["cache-control"] == "no-store"


def test_metrics_token_is_never_echoed(settings: Settings) -> None:
    token = "d" * 40
    guarded = settings.model_copy(update={"metrics_token": SecretStr(token)})
    with _client(guarded) as client:
        denied = client.get("/metrics")

    assert token not in denied.text


def test_worker_metrics_require_multiprocess_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)

    assert start_worker_metrics_server("127.0.0.1", 9101) is False


def test_settings_reject_short_metrics_token() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql://u:p@localhost/db",
            redis_url="redis://localhost:6379/0",
            api_key_pepper="a" * 40,
            jwt_secret="b" * 40,
            webhook_secret_key="c" * 40,
            metrics_token="short",
        )


def test_worker_metrics_server_aggregates_when_multiprocess_is_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import packages.core.observability as observability

    calls: dict[str, object] = {}

    def fake_collector(registry: object) -> None:
        calls["registry"] = registry

    def fake_server(port: int, addr: str, registry: object) -> None:
        calls["port"] = port
        calls["addr"] = addr
        calls["server_registry"] = registry

    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    monkeypatch.setattr(observability.multiprocess, "MultiProcessCollector", fake_collector)
    monkeypatch.setattr(observability, "start_http_server", fake_server)

    assert start_worker_metrics_server("127.0.0.1", 9999) is True
    assert calls["port"] == 9999
    assert calls["addr"] == "127.0.0.1"
    assert calls["registry"] is calls["server_registry"]
