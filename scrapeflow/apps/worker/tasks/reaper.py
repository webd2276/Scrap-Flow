"""Reaper: requeue lost jobs and clean stale browser sessions."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import structlog
from packages.core.models import Job, JobStatus
from packages.core.quota import settle_job_usage
from packages.core.settings import Settings, get_settings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.services.dispatch import RUN_JOB_TASK
from apps.worker import job_store
from apps.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)

REAPER_LOCK = "sf:reaper:lock"
SESSION_PREFIX = "sf:browser:session:"


async def _delete_grid_session(settings: Settings, session_id: str) -> None:
    if not settings.selenium_remote_url or not session_id:
        return
    url = f"{settings.selenium_remote_url.rstrip('/')}/session/{session_id}"
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            await client.delete(url)
    except httpx.HTTPError:
        logger.warning("reaper.grid_delete_failed", session_id=session_id)


async def _clean_sessions(
    settings: Settings,
    maker: async_sessionmaker[AsyncSession],
    redis: Redis,
) -> int:
    cleaned = 0
    keys = [key async for key in redis.scan_iter(f"{SESSION_PREFIX}*")]
    for key in keys:
        raw_job_id = key.rsplit(":", 1)[-1]
        try:
            job_id = uuid.UUID(raw_job_id)
        except ValueError:
            await redis.delete(key)
            continue
        session_id = await redis.get(key)
        async with maker() as session:
            job = await session.get(Job, job_id)
        terminal = job is None or job.status in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMED_OUT,
        }
        if terminal:
            if session_id:
                await _delete_grid_session(settings, session_id)
            await redis.delete(key)
            cleaned += 1
    return cleaned


async def _reap(
    *,
    settings: Settings | None = None,
    dispatch_job: Callable[[uuid.UUID], None] | None = None,
) -> dict[str, int]:
    settings = settings or get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    lock_seconds = max(5, settings.job_reaper_interval_seconds - 2)
    try:
        acquired = await redis.set(REAPER_LOCK, "1", nx=True, ex=lock_seconds)
        if not acquired:
            return {"skipped": 1}
        maker = job_store.sessionmaker(settings)
        now = datetime.now(UTC)
        dispatch: list[uuid.UUID] = []
        terminal: list[Job] = []
        requeued = 0
        failed = 0
        async with maker() as session:
            for job in await job_store.expired_running_jobs(session, now=now):
                if job.cancel_requested_at is not None:
                    job.status = JobStatus.CANCELLED
                    job.finished_at = now
                    job.lease_expires_at = None
                    job.worker_id = None
                    job.error_code = None
                    job.error_message = None
                    job_store.add_event(
                        session,
                        job_id=job.id,
                        event_type="cancelled",
                        message="Job cancelled after the worker lease expired",
                    )
                    terminal.append(job)
                    continue
                job.lease_expires_at = None
                job.worker_id = None
                if job.attempts < job.max_attempts:
                    job.status = JobStatus.QUEUED
                    job_store.add_event(
                        session,
                        job_id=job.id,
                        event_type="requeued",
                        message="Worker lease expired; job requeued",
                        data={"attempts": job.attempts},
                    )
                    dispatch.append(job.id)
                    requeued += 1
                else:
                    job.status = JobStatus.FAILED
                    job.error_code = "WORKER_LOST"
                    job.error_message = "Worker lease expired and attempts are exhausted"
                    job.finished_at = now
                    if job.started_at is not None:
                        job.duration_ms = int((now - job.started_at).total_seconds() * 1000)
                    job_store.add_event(
                        session,
                        job_id=job.id,
                        event_type="failed",
                        message="Worker lease expired; no attempts remain",
                        data={"error_code": "WORKER_LOST"},
                    )
                    terminal.append(job)
                    failed += 1
            stale = await job_store.stale_queued_jobs(
                session,
                now=now,
                older_than_seconds=settings.job_queued_stale_seconds,
            )
            dispatch.extend(job.id for job in stale)
            await session.commit()

        for job in terminal:
            async with maker() as session:
                await settle_job_usage(session, redis, job=job)

        for job_id in dict.fromkeys(dispatch):
            if dispatch_job is not None:
                dispatch_job(job_id)
            else:
                celery_app.send_task(RUN_JOB_TASK, args=[str(job_id)], queue="jobs")
        cleaned = await _clean_sessions(settings, maker, redis)
        logger.info(
            "reaper.completed",
            requeued=requeued,
            failed=failed,
            dispatched=len(dispatch),
            sessions_cleaned=cleaned,
        )
        return {
            "requeued": requeued,
            "failed": failed,
            "dispatched": len(dispatch),
            "sessions_cleaned": cleaned,
        }
    finally:
        await redis.aclose()


@celery_app.task(name="scrapeflow.reap")  # type: ignore[untyped-decorator]
def reap() -> dict[str, int]:
    return asyncio.run(_reap())
