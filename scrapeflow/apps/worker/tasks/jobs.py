"""Celery task that executes one durable job."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any

import structlog
from celery.exceptions import SoftTimeLimitExceeded
from packages.core.errors import AppError, ErrorCode
from packages.core.models import JobStatus
from packages.core.settings import Settings, get_settings
from packages.core.ssrf import SSRFPolicy

from apps.api.services.dispatch import RUN_JOB_TASK
from apps.worker import job_store
from apps.worker.celery_app import celery_app
from apps.worker.scrape import artifact_expiry, execute_scrape

logger = structlog.get_logger(__name__)


def _worker_id() -> str:
    return f"{os.uname().nodename}:{os.getpid()}"


async def _run_job(
    job_id: uuid.UUID,
    worker_id: str,
    *,
    settings: Settings | None = None,
    policy: SSRFPolicy | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    maker = job_store.sessionmaker(settings)

    async with maker() as session:
        job = await job_store.claim_job(
            session,
            job_id=job_id,
            worker_id=worker_id,
            settings=settings,
        )
    if job is None:
        return {"job_id": str(job_id), "status": "ignored"}

    if job.cancel_requested_at is not None:
        async with maker() as session:
            await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.CANCELLED,
                event_message="Job cancelled before execution",
            )
        return {"job_id": str(job_id), "status": JobStatus.CANCELLED.value}

    timeout = int(job.payload.get("timeout_seconds") or settings.job_timeout_seconds)
    deadline = time.monotonic() + timeout
    try:
        outcome = await execute_scrape(
            job=job,
            settings=settings,
            sessionmaker=maker,
            deadline=deadline,
            policy=policy,
        )
        async with maker() as session:
            for artifact in outcome.artifacts:
                await job_store.add_artifact(
                    session,
                    org_id=job.org_id,
                    job_id=job.id,
                    kind=artifact.kind,
                    filename=artifact.filename,
                    content_type=artifact.content_type,
                    size_bytes=artifact.stored.size_bytes,
                    sha256=artifact.stored.sha256,
                    storage_key=artifact.stored.storage_key,
                    expires_at=artifact_expiry(settings),
                )
            cancelled = await job_store.cancel_requested(session, job.id)
            if cancelled:
                await job_store.finish_job(
                    session,
                    job_id=job.id,
                    status=JobStatus.CANCELLED,
                    result=outcome.result,
                    event_message="Job cancelled before completion",
                )
                return {"job_id": str(job_id), "status": JobStatus.CANCELLED.value}
            await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.SUCCEEDED,
                result=outcome.result,
                event_message="Job completed",
            )
        return {
            "job_id": str(job_id),
            "status": JobStatus.SUCCEEDED.value,
            "artifacts": len(outcome.artifacts),
        }
    except AppError as exc:
        status = JobStatus.TIMED_OUT if exc.code == ErrorCode.TIMEOUT else JobStatus.FAILED
        async with maker() as session:
            await job_store.finish_job(
                session,
                job_id=job.id,
                status=status,
                error_code=exc.code.value,
                error_message=exc.message,
                error_details=exc.details if isinstance(exc.details, dict) else None,
            )
        logger.warning(
            "job.failed",
            job_id=str(job_id),
            code=exc.code.value,
            message=exc.message,
        )
        return {"job_id": str(job_id), "status": status.value, "error": exc.code.value}
    except SoftTimeLimitExceeded:
        async with maker() as session:
            await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.TIMED_OUT,
                error_code=ErrorCode.TIMEOUT.value,
                error_message="Job exceeded the worker time limit",
            )
        return {"job_id": str(job_id), "status": JobStatus.TIMED_OUT.value}
    except TimeoutError:
        async with maker() as session:
            await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.TIMED_OUT,
                error_code=ErrorCode.TIMEOUT.value,
                error_message="Job exceeded its deadline",
            )
        return {"job_id": str(job_id), "status": JobStatus.TIMED_OUT.value}
    except Exception as exc:
        logger.exception("job.internal_error", job_id=str(job_id))
        async with maker() as session:
            await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.FAILED,
                error_code=ErrorCode.INTERNAL_ERROR.value,
                error_message="Internal worker error",
                error_details={"exception": type(exc).__name__},
            )
        return {
            "job_id": str(job_id),
            "status": JobStatus.FAILED.value,
            "error": ErrorCode.INTERNAL_ERROR.value,
        }


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name=RUN_JOB_TASK,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=get_settings().job_timeout_seconds + 5,
    time_limit=get_settings().job_timeout_seconds + 30,
)
def run_job(self: Any, job_id: str) -> dict[str, Any]:
    return asyncio.run(_run_job(uuid.UUID(job_id), _worker_id()))
