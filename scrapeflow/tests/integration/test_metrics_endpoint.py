from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from tests.integration.conftest import auth_header, signup_payload


def _signup(client: TestClient) -> dict[str, str]:
    response = client.post("/v1/auth/signup", json=signup_payload())
    assert response.status_code == 201, response.text
    return auth_header(response.json()["access_token"])


def test_metrics_samples_queue_sessions_and_dependencies(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.text
    assert 'scrapeflow_queue_depth{queue="jobs"}' in body
    assert 'scrapeflow_queue_depth{queue="celery"}' in body
    assert "scrapeflow_active_browser_sessions" in body
    assert "scrapeflow_db_latency_seconds" in body
    assert "scrapeflow_redis_latency_seconds" in body
    assert "scrapeflow_webhook_pending" in body


def test_quota_rejections_are_counted(client: TestClient) -> None:
    headers = _signup(client)
    payload: dict[str, Any] = {
        "url": "https://example.com/",
        "render_js": False,
        "extract": {"text": True},
    }

    first = client.post("/v1/scrape", json=payload, headers=headers)
    second = client.post("/v1/scrape", json=payload, headers=headers)

    assert first.status_code == 202, first.text
    assert second.status_code == 429, second.text
    assert second.json()["error"]["code"] == "CONCURRENCY_LIMIT"
    body = client.get("/metrics").text
    assert 'scrapeflow_quota_rejections_total{reason="concurrency"}' in body
