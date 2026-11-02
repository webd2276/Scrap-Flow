"""Celery application: job queue, reaper schedule, and durable delivery."""

from __future__ import annotations

from celery import Celery
from packages.core.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "scrapeflow",
    broker=settings.redis_url,
    include=[
        "apps.worker.tasks.health",
        "apps.worker.tasks.jobs",
        "apps.worker.tasks.reaper",
        "apps.worker.tasks.reconcile",
        "apps.worker.tasks.retention",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
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
    },
    broker_transport_options={
        "visibility_timeout": max(settings.job_lease_seconds * 2, 600),
    },
)
