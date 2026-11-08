"""Celery application: job queue, reaper schedule, and durable delivery."""

from __future__ import annotations

from typing import Any

import structlog
from celery import Celery
from celery.signals import worker_ready
from packages.core.logging import configure_logging
from packages.core.observability import start_worker_metrics_server
from packages.core.settings import get_settings

settings = get_settings()
configure_logging(settings)
logger = structlog.get_logger(__name__)

celery_app = Celery(
    "scrapeflow",
    broker=settings.redis_url,
    include=[
        "apps.worker.tasks.health",
        "apps.worker.tasks.jobs",
        "apps.worker.tasks.reaper",
        "apps.worker.tasks.reconcile",
        "apps.worker.tasks.retention",
        "apps.worker.tasks.schedules",
        "apps.worker.tasks.webhooks",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_hijack_root_logger=False,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    result_backend=None,
    timezone="UTC",
    enable_utc=True,
    task_create_missing_queues=True,
    task_default_queue="celery",
    task_routes={
        "scrapeflow.run_job": {"queue": "jobs"},
        "scrapeflow.reap": {"queue": "celery"},
        "scrapeflow.reconcile_quotas": {"queue": "celery"},
        "scrapeflow.purge_artifacts": {"queue": "celery"},
        "scrapeflow.dispatch_schedules": {"queue": "celery"},
        "scrapeflow.deliver_webhooks": {"queue": "celery"},
    },
    beat_schedule={
        "reap-lost-jobs": {
            "task": "scrapeflow.reap",
            "schedule": float(settings.job_reaper_interval_seconds),
        },
        "reconcile-quotas": {
            "task": "scrapeflow.reconcile_quotas",
            "schedule": float(settings.quota_reconcile_interval_seconds),
        },
        "purge-expired-artifacts": {
            "task": "scrapeflow.purge_artifacts",
            "schedule": float(settings.artifact_retention_interval_seconds),
        },
        "dispatch-schedules": {
            "task": "scrapeflow.dispatch_schedules",
            "schedule": float(settings.schedule_dispatch_interval_seconds),
        },
        "deliver-webhooks": {
            "task": "scrapeflow.deliver_webhooks",
            "schedule": float(settings.webhook_dispatch_interval_seconds),
        },
    },
    broker_transport_options={
        "visibility_timeout": max(settings.job_lease_seconds * 2, 600),
    },
)


@worker_ready.connect  # type: ignore[untyped-decorator]
def _start_metrics_server(**_: Any) -> None:
    if not settings.worker_metrics_enabled:
        return
    started = start_worker_metrics_server(
        settings.worker_metrics_host,
        settings.worker_metrics_port,
    )
    if not started:
        logger.warning(
            "worker.metrics_unavailable",
            reason="PROMETHEUS_MULTIPROC_DIR is required",
        )
