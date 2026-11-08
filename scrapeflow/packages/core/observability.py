"""Prometheus metrics shared by the API and worker.

The API exposes the default registry at ``/metrics``. Workers run with
``PROMETHEUS_MULTIPROC_DIR`` set so each prefork child writes its counters to
the shared directory; ``start_worker_metrics_server`` then aggregates them with
``MultiProcessCollector``. Without multiprocess mode the worker endpoint is not
started because it would only show the parent process.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
    start_http_server,
)

logger = structlog.get_logger(__name__)


def _prepare_multiprocess_dir() -> None:
    """Clear stale worker metric shards before the prefork pool starts.

    This runs at import time in the worker parent. Removing files after the pool
    has forked would delete live mmap files, so do it before any metric value is
    created.
    """
    configured = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if not configured:
        return
    directory = Path(configured)
    directory.mkdir(parents=True, exist_ok=True)
    for entry in directory.iterdir():
        if entry.is_file():
            entry.unlink(missing_ok=True)


_prepare_multiprocess_dir()

HTTP_REQUESTS_TOTAL = Counter(
    "scrapeflow_http_requests_total",
    "HTTP requests handled by the API.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "scrapeflow_http_request_duration_seconds",
    "API request latency in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
JOBS_TOTAL = Counter(
    "scrapeflow_jobs_total",
    "Jobs that reached a terminal state.",
    ("kind", "status"),
)
JOB_FAILURES_TOTAL = Counter(
    "scrapeflow_job_failures_total",
    "Terminal job failures by typed error code.",
    ("kind", "code"),
)
JOB_DURATION_SECONDS = Histogram(
    "scrapeflow_job_duration_seconds",
    "Job execution time in seconds, from claim to terminal state.",
    ("kind", "status"),
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)
QUEUE_DEPTH = Gauge(
    "scrapeflow_queue_depth",
    "Messages waiting in a Celery queue (sampled when /metrics is scraped).",
    ("queue",),
)
ACTIVE_BROWSER_SESSIONS = Gauge(
    "scrapeflow_active_browser_sessions",
    "Browser sessions currently registered in Redis.",
    multiprocess_mode="livesum",
)
WEBHOOK_DELIVERIES_TOTAL = Counter(
    "scrapeflow_webhook_deliveries_total",
    "Webhook delivery attempts by event and result.",
    ("event", "result"),
)
WEBHOOK_PENDING = Gauge(
    "scrapeflow_webhook_pending",
    "Webhook deliveries waiting for an attempt (sampled at scrape time).",
    multiprocess_mode="livesum",
)
QUOTA_REJECTIONS_TOTAL = Counter(
    "scrapeflow_quota_rejections_total",
    "Job submissions rejected by plan limits.",
    ("reason",),
)
RATE_LIMIT_HITS_TOTAL = Counter(
    "scrapeflow_rate_limit_hits_total",
    "Requests rejected by a rate limiter.",
    ("scope",),
)
DB_LATENCY_SECONDS = Gauge(
    "scrapeflow_db_latency_seconds",
    "Duration of the readiness query issued while scraping /metrics.",
)
REDIS_LATENCY_SECONDS = Gauge(
    "scrapeflow_redis_latency_seconds",
    "PING latency observed while scraping /metrics.",
)


def observe_http_request(
    *,
    method: str,
    route: str,
    status: int,
    duration_seconds: float,
) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=str(status)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, route=route).observe(duration_seconds)


def record_job_completion(
    *,
    kind: str,
    status: str,
    duration_seconds: float | None,
    error_code: str | None = None,
) -> None:
    JOBS_TOTAL.labels(kind=kind, status=status).inc()
    if duration_seconds is not None:
        JOB_DURATION_SECONDS.labels(kind=kind, status=status).observe(duration_seconds)
    if error_code:
        JOB_FAILURES_TOTAL.labels(kind=kind, code=error_code).inc()


def record_webhook_delivery(*, event: str, result: str) -> None:
    WEBHOOK_DELIVERIES_TOTAL.labels(event=event, result=result).inc()


def record_quota_rejection(*, reason: str) -> None:
    QUOTA_REJECTIONS_TOTAL.labels(reason=reason).inc()


def record_rate_limit_hit(*, scope: str) -> None:
    RATE_LIMIT_HITS_TOTAL.labels(scope=scope).inc()


def render_metrics() -> tuple[bytes, str]:
    """Return the exposition payload and its content type."""
    return generate_latest(), CONTENT_TYPE_LATEST


def start_worker_metrics_server(host: str, port: int) -> bool:
    """Expose aggregated worker metrics; requires multiprocess mode.

    Returns ``True`` when the HTTP server was started. Celery prefork children
    hold the counters, so a process-local endpoint would be misleading; refuse
    to start without ``PROMETHEUS_MULTIPROC_DIR`` and let the caller log it.
    """
    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        return False
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
    start_http_server(port, addr=host, registry=registry)
    logger.info("worker.metrics_started", host=host, port=port)
    return True
