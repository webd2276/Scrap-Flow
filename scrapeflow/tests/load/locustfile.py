"""Locust load profile for a staging ScrapeFlow deployment.

Run against a staging stack, never production, with a dedicated API key whose
plan allows the concurrency you intend to generate:

    LOAD_API_KEY=sf_live_... LOAD_TARGET_URL=https://example.com \
        .venv/bin/locust -f tests/load/locustfile.py --host https://staging.example.com \
        --users 25 --spawn-rate 5 --run-time 5m --headless

The target URL must be reachable by the worker through the egress proxy. The
profile submits scrape jobs, polls their status, and reads health, usage, and
metrics so queue depth, latency, and error rate are exercised together.
"""

from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, events, task

API_KEY = os.getenv("LOAD_API_KEY", "")
TARGET_URL = os.getenv("LOAD_TARGET_URL", "https://example.com")
BASE_URL = os.getenv("LOAD_BASE_URL", "http://127.0.0.1:8000")


@events.test_start.add_listener
def _require_api_key(environment: object, **kwargs: object) -> None:
    if not API_KEY:
        raise RuntimeError("LOAD_API_KEY is required; use a dedicated staging key")


class ScrapeFlowUser(HttpUser):
    host = BASE_URL
    wait_time = between(1, 4)

    def on_start(self) -> None:
        self.client.headers.update(
            {
                "X-API-Key": API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        self.job_ids: list[str] = []

    @task(10)
    def submit_scrape(self) -> None:
        payload = {
            "url": TARGET_URL,
            "render_js": False,
            "extract": {"text": True},
            "timeout_seconds": 60,
        }
        with self.client.post(
            "/v1/scrape",
            json=payload,
            headers={"Idempotency-Key": uuid.uuid4().hex},
            name="/v1/scrape",
            catch_response=True,
        ) as response:
            if response.status_code != 202:
                response.failure(f"unexpected status {response.status_code}")
                return
            body = response.json()
            job_id = body.get("job_id")
            if not job_id:
                response.failure("missing job_id")
                return
            self.job_ids.append(job_id)
            del self.job_ids[:-25]

    @task(6)
    def poll_job(self) -> None:
        if not self.job_ids:
            return
        job_id = self.job_ids[-1]
        response = self.client.get(f"/v1/jobs/{job_id}", name="/v1/jobs/[id]")
        if response.status_code == 200:
            status = response.json().get("status")
            if status in {"succeeded", "failed", "cancelled", "timed_out"}:
                self.job_ids.remove(job_id)

    @task(2)
    def list_jobs(self) -> None:
        self.client.get("/v1/jobs?limit=20", name="/v1/jobs")

    @task(1)
    def read_usage(self) -> None:
        self.client.get("/v1/usage", name="/v1/usage")

    @task(5)
    def health(self) -> None:
        self.client.get("/health", name="/health")

    @task(1)
    def metrics(self) -> None:
        token = os.getenv("LOAD_METRICS_TOKEN", "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client.get("/metrics", headers=headers, name="/metrics")
