"""Job dispatch boundary.

The API never imports browser or Selenium code. It only sends a task name to
Celery. If the broker is unavailable the job stays ``queued`` in PostgreSQL and
the reaper dispatches it later, so accepting a job is durable even when Redis is
briefly down.
"""

from __future__ import annotations

import uuid
from typing import Protocol

import structlog
from packages.core.settings import Settings

logger = structlog.get_logger(__name__)

RUN_JOB_TASK = "scrapeflow.run_job"


class JobDispatcher(Protocol):
    def enqueue(self, job_id: uuid.UUID) -> bool: ...


class NullDispatcher:
    def enqueue(self, job_id: uuid.UUID) -> bool:
        logger.info("job.dispatch.disabled", job_id=str(job_id))
        return False


class CeleryJobDispatcher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def enqueue(self, job_id: uuid.UUID) -> bool:
        if not self._settings.queue_enabled:
            logger.info("job.dispatch.disabled", job_id=str(job_id))
            return False
        try:
            from apps.worker.celery_app import celery_app

            celery_app.send_task(
                RUN_JOB_TASK,
                args=[str(job_id)],
                queue="jobs",
            )
        except Exception:
            # The row is already committed as queued; reaper will pick it up.
            logger.exception("job.dispatch.failed", job_id=str(job_id))
            return False
        return True
