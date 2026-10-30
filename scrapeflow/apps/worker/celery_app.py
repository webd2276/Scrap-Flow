"""Celery application. Tasks are added in later phases."""

from __future__ import annotations

from celery import Celery
from packages.core.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "scrapeflow",
    broker=settings.redis_url,
    include=["apps.worker.tasks.health"],
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
)
