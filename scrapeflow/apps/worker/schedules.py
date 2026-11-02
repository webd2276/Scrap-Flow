"""Cron dispatch and post-run change detection."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from packages.core.errors import AppError
from packages.core.models import (
    Job,
    JobStatus,
    Organization,
    Schedule,
    ScheduleRun,
    ScheduleRunStatus,
)
from packages.core.schedules import compute_changes, extract_values, next_run_after
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.services.dispatch import RUN_JOB_TASK
from apps.api.services.schedules import create_job_for_schedule, record_skipped
from apps.worker import job_store
from apps.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)

DISPATCH_LOCK = "sf:schedules:dispatch:lock"

_TERMINAL_RUN_STATUS = {
    JobStatus.SUCCEEDED: ScheduleRunStatus.SUCCEEDED,
    JobStatus.FAILED: ScheduleRunStatus.FAILED,
    JobStatus.TIMED_OUT: ScheduleRunStatus.FAILED,
    JobStatus.CANCELLED: ScheduleRunStatus.CANCELLED,
}


def dispatch_policy(settings: Settings) -> SSRFPolicy:
    return SSRFPolicy(allowed_ports=settings.egress_port_set)


async def dispatch_due_schedules(
    *,
    settings: Settings,
    redis: Redis,
    dispatch_job: Callable[[uuid.UUID], None] | None = None,
) -> dict[str, int]:
    maker = job_store.sessionmaker(settings)
    policy = dispatch_policy(settings)
    now = datetime.now(UTC)
    async with maker() as session:
        due_ids = list(
            (
                await session.execute(
                    select(Schedule.id)
                    .where(
                        Schedule.enabled.is_(True),
                        Schedule.next_run_at <= now,
                    )
                    .order_by(Schedule.next_run_at, Schedule.id)
                    .limit(settings.schedule_dispatch_batch_size)
                )
            ).scalars()
        )

    dispatched = 0
    skipped = 0
    for schedule_id in due_ids:
        # Claim the occurrence first. The unique run_key makes a crashed or
        # concurrent dispatcher unable to create a second job for it.
        try:
            async with maker() as session:
                schedule = (
                    await session.execute(
                        select(Schedule).where(Schedule.id == schedule_id).with_for_update()
                    )
                ).scalar_one_or_none()
                if schedule is None or not schedule.enabled or schedule.next_run_at > now:
                    continue
                scheduled_for = schedule.next_run_at
                run_key = f"cron:{schedule.id}:{scheduled_for.isoformat()}"
                schedule.next_run_at = next_run_after(schedule.cron, schedule.timezone, now)
                run = ScheduleRun(
                    org_id=schedule.org_id,
                    schedule_id=schedule.id,
                    run_key=run_key,
                    trigger="cron",
                    status=ScheduleRunStatus.QUEUED,
                    scheduled_for=scheduled_for,
                )
                session.add(run)
                await session.flush()
                run_id = run.id
                await session.commit()
        except Exception:
            logger.exception("schedule.claim_failed", schedule_id=str(schedule_id))
            skipped += 1
            continue

        job_id: uuid.UUID | None = None
        org_id: uuid.UUID | None = None
        try:
            async with maker() as session:
                schedule = await session.get(Schedule, schedule_id)
                if schedule is None:  # pragma: no cover - deleted after claim
                    continue
                org = await session.get(Organization, schedule.org_id)
                if org is None:  # pragma: no cover - cascade guarantees an org
                    continue
                org_id = schedule.org_id
                try:
                    job, _replay, _state = await create_job_for_schedule(
                        session,
                        schedule=schedule,
                        org=org,
                        settings=settings,
                        policy=policy,
                        redis=redis,
                        run_key=run_key,
                        request_id=f"schedule:{run_id}",
                        commit=False,
                    )
                except AppError as exc:
                    await session.rollback()
                    await record_skipped(
                        session,
                        schedule_id=schedule_id,
                        org_id=org_id,
                        run_key=run_key,
                        scheduled_for=scheduled_for,
                        trigger="cron",
                        error=f"{exc.code.value}: {exc.message}",
                    )
                    skipped += 1
                    logger.info(
                        "schedule.skipped",
                        schedule_id=str(schedule_id),
                        code=exc.code.value,
                    )
                    continue
                stored_run = await session.get(ScheduleRun, run_id)
                if stored_run is not None:
                    stored_run.job_id = job.id
                    stored_run.credits = job.credits
                schedule.last_run_at = scheduled_for
                schedule.last_job_id = job.id
                schedule.last_error = None
                await session.commit()
                job_id = job.id
        except Exception as exc:
            logger.exception(
                "schedule.dispatch_failed", schedule_id=str(schedule_id), run_id=str(run_id)
            )
            skipped += 1
            if org_id is not None:
                try:
                    async with maker() as session:
                        await record_skipped(
                            session,
                            schedule_id=schedule_id,
                            org_id=org_id,
                            run_key=run_key,
                            scheduled_for=scheduled_for,
                            trigger="cron",
                            error=f"{type(exc).__name__}: {exc}"[:2000],
                        )
                except Exception:
                    logger.exception(
                        "schedule.skip_record_failed",
                        schedule_id=str(schedule_id),
                        run_id=str(run_id),
                    )
            continue

        if job_id is not None:
            if dispatch_job is not None:
                dispatch_job(job_id)
            else:
                celery_app.send_task(RUN_JOB_TASK, args=[str(job_id)], queue="jobs")
            dispatched += 1

    return {"dispatched": dispatched, "skipped": skipped, "due": len(due_ids)}


async def record_terminal_job(
    session: AsyncSession,
    *,
    job: Job,
) -> tuple[ScheduleRun, list[dict[str, Any]]] | None:
    """Attach a finished job to its schedule run and compute watched-field diffs."""
    if job.schedule_id is None:
        return None
    run = (
        await session.execute(select(ScheduleRun).where(ScheduleRun.job_id == job.id))
    ).scalar_one_or_none()
    if run is None and job.idempotency_key:
        run = (
            await session.execute(
                select(ScheduleRun).where(ScheduleRun.run_key == job.idempotency_key)
            )
        ).scalar_one_or_none()
    if run is None:
        logger.warning("schedule.run_missing", job_id=str(job.id))
        return None
    schedule = await session.get(Schedule, job.schedule_id)
    if schedule is None:  # pragma: no cover - FK is SET NULL
        return None

    finished = job.finished_at or datetime.now(UTC)
    run.status = _TERMINAL_RUN_STATUS.get(job.status, ScheduleRunStatus.FAILED)
    run.finished_at = finished
    run.credits = job.credits
    changes: list[dict[str, Any]] = []
    if job.status is JobStatus.SUCCEEDED:
        fields = list(schedule.watched_fields)
        if fields:
            previous = (
                await session.execute(
                    select(ScheduleRun)
                    .where(
                        ScheduleRun.schedule_id == schedule.id,
                        ScheduleRun.id != run.id,
                        ScheduleRun.scheduled_for < run.scheduled_for,
                        ScheduleRun.values.is_not(None),
                    )
                    .order_by(ScheduleRun.created_at.desc(), ScheduleRun.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            values = extract_values(job.result or {}, fields)
            changes = compute_changes(previous.values if previous is not None else None, values)
            run.values = values
            run.changes = changes
        schedule.last_error = None
    else:
        schedule.last_error = (job.error_message or run.status.value)[:2000]
    schedule.last_run_at = finished
    schedule.last_job_id = job.id
    return run, changes


async def process_terminal_job(
    maker: async_sessionmaker[AsyncSession],
    *,
    job_id: uuid.UUID,
    settings: Settings,
) -> None:
    """Post-terminal hook for webhooks and schedule history; never fails a job."""
    from apps.worker.webhooks import enqueue_job_webhooks, enqueue_schedule_changed

    try:
        async with maker() as session:
            job = await session.get(Job, job_id)
            if job is None or job.status not in _TERMINAL_RUN_STATUS:
                return
            scheduled = await record_terminal_job(session, job=job)
            await enqueue_job_webhooks(session, job=job, settings=settings)
            if scheduled is not None:
                run, changes = scheduled
                schedule = (
                    await session.get(Schedule, job.schedule_id)
                    if job.schedule_id is not None
                    else None
                )
                if changes and schedule is not None and schedule.notify_on_change:
                    await enqueue_schedule_changed(
                        session,
                        schedule=schedule,
                        run=run,
                        changes=changes,
                        settings=settings,
                    )
            await session.commit()
    except Exception:
        logger.exception("schedule.post_terminal_failed", job_id=str(job_id))
