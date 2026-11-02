"""Celery task that executes one durable job."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from celery.exceptions import SoftTimeLimitExceeded
from packages.core.errors import AppError, ErrorCode
from packages.core.models import Job, JobKind, JobStatus, Organization
from packages.core.plans import plan_for
from packages.core.quota import settle_job_usage
from packages.core.settings import Settings, get_settings
from packages.core.ssrf import SSRFPolicy
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.services.dispatch import RUN_JOB_TASK
from apps.worker import job_store
from apps.worker.automate import AutomationOutcome, execute_automation
from apps.worker.celery_app import celery_app
from apps.worker.http_fetch import JobCancelledError
from apps.worker.scrape import ProducedArtifact, execute_scrape

logger = structlog.get_logger(__name__)


def _worker_id() -> str:
    return f"{os.uname().nodename}:{os.getpid()}"


async def _record_artifacts(
    maker: async_sessionmaker[AsyncSession],
    *,
    job: Job,
    artifacts: tuple[ProducedArtifact, ...],
    settings: Settings,
) -> None:
    async with maker() as session:
        plan = await session.scalar(select(Organization.plan).where(Organization.id == job.org_id))
        retention_days = (
            plan_for(plan).artifact_retention_days
            if plan is not None
            else settings.artifacts_retention_days
        )
        expires_at = datetime.now(UTC) + timedelta(days=retention_days)
        for artifact in artifacts:
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
                expires_at=expires_at,
            )


async def _settle_job(
    session: AsyncSession,
    *,
    job: Job,
    settings: Settings,
    started: bool | None = None,
) -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await settle_job_usage(session, redis, job=job, started=started)
    finally:
        await redis.aclose()


async def _finish_automation(
    maker: async_sessionmaker[AsyncSession],
    *,
    job: Job,
    outcome: AutomationOutcome,
    settings: Settings,
) -> JobStatus:
    async with maker() as session:
        cancelled = await job_store.cancel_requested(session, job.id)
        if cancelled:
            finished = await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.CANCELLED,
                result=outcome.result,
                event_message="Job cancelled before completion",
            )
            if finished is not None:
                await _settle_job(session, job=finished, settings=settings)
            return JobStatus.CANCELLED
        if outcome.failure is not None:
            failure = outcome.failure
            status = JobStatus.TIMED_OUT if failure.code == ErrorCode.TIMEOUT else JobStatus.FAILED
            finished = await job_store.finish_job(
                session,
                job_id=job.id,
                status=status,
                result=outcome.result,
                error_code=failure.code.value,
                error_message=failure.message,
                error_details=failure.details if isinstance(failure.details, dict) else None,
            )
            if finished is not None:
                await _settle_job(session, job=finished, settings=settings)
            return status
        finished = await job_store.finish_job(
            session,
            job_id=job.id,
            status=JobStatus.SUCCEEDED,
            result=outcome.result,
            event_message="Job completed",
        )
        if finished is not None:
            await _settle_job(session, job=finished, settings=settings)
        return JobStatus.SUCCEEDED


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
            finished = await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.CANCELLED,
                event_message="Job cancelled before execution",
            )
            if finished is not None:
                await _settle_job(session, job=finished, settings=settings, started=False)
        return {"job_id": str(job_id), "status": JobStatus.CANCELLED.value}

    timeout = int(job.payload.get("timeout_seconds") or settings.job_timeout_seconds)
    deadline = time.monotonic() + timeout
    try:
        if job.kind == JobKind.AUTOMATION:
            outcome = await execute_automation(
                job=job,
                settings=settings,
                sessionmaker=maker,
                deadline=deadline,
                policy=policy,
            )
            await _record_artifacts(maker, job=job, artifacts=outcome.artifacts, settings=settings)
            status = await _finish_automation(maker, job=job, outcome=outcome, settings=settings)
            payload: dict[str, Any] = {
                "job_id": str(job_id),
                "status": status.value,
                "artifacts": len(outcome.artifacts),
            }
            if outcome.failure is not None:
                payload["error"] = outcome.failure.code.value
            return payload

        scrape_outcome = await execute_scrape(
            job=job,
            settings=settings,
            sessionmaker=maker,
            deadline=deadline,
            policy=policy,
        )
        await _record_artifacts(
            maker, job=job, artifacts=scrape_outcome.artifacts, settings=settings
        )
        async with maker() as session:
            cancelled = await job_store.cancel_requested(session, job.id)
            if cancelled:
                finished = await job_store.finish_job(
                    session,
                    job_id=job.id,
                    status=JobStatus.CANCELLED,
                    result=scrape_outcome.result,
                    event_message="Job cancelled before completion",
                )
                if finished is not None:
                    await _settle_job(session, job=finished, settings=settings)
                return {"job_id": str(job_id), "status": JobStatus.CANCELLED.value}
            finished = await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.SUCCEEDED,
                result=scrape_outcome.result,
                event_message="Job completed",
            )
            if finished is not None:
                await _settle_job(session, job=finished, settings=settings)
        return {
            "job_id": str(job_id),
            "status": JobStatus.SUCCEEDED.value,
            "artifacts": len(scrape_outcome.artifacts),
        }
    except JobCancelledError:
        async with maker() as session:
            finished = await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.CANCELLED,
                event_message="Job cancelled during execution",
            )
            if finished is not None:
                await _settle_job(session, job=finished, settings=settings)
        return {"job_id": str(job_id), "status": JobStatus.CANCELLED.value}
    except AppError as exc:
        status = JobStatus.TIMED_OUT if exc.code == ErrorCode.TIMEOUT else JobStatus.FAILED
        async with maker() as session:
            finished = await job_store.finish_job(
                session,
                job_id=job.id,
                status=status,
                error_code=exc.code.value,
                error_message=exc.message,
                error_details=exc.details if isinstance(exc.details, dict) else None,
            )
            if finished is not None:
                await _settle_job(session, job=finished, settings=settings)
        logger.warning(
            "job.failed",
            job_id=str(job_id),
            code=exc.code.value,
            message=exc.message,
        )
        return {"job_id": str(job_id), "status": status.value, "error": exc.code.value}
    except SoftTimeLimitExceeded:
        async with maker() as session:
            finished = await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.TIMED_OUT,
                error_code=ErrorCode.TIMEOUT.value,
                error_message="Job exceeded the worker time limit",
            )
            if finished is not None:
                await _settle_job(session, job=finished, settings=settings)
        return {"job_id": str(job_id), "status": JobStatus.TIMED_OUT.value}
    except TimeoutError:
        async with maker() as session:
            finished = await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.TIMED_OUT,
                error_code=ErrorCode.TIMEOUT.value,
                error_message="Job exceeded its deadline",
            )
            if finished is not None:
                await _settle_job(session, job=finished, settings=settings)
        return {"job_id": str(job_id), "status": JobStatus.TIMED_OUT.value}
    except Exception as exc:
        logger.exception("job.internal_error", job_id=str(job_id))
        async with maker() as session:
            finished = await job_store.finish_job(
                session,
                job_id=job.id,
                status=JobStatus.FAILED,
                error_code=ErrorCode.INTERNAL_ERROR.value,
                error_message="Internal worker error",
                error_details={"exception": type(exc).__name__},
            )
            if finished is not None:
                await _settle_job(session, job=finished, settings=settings)
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
