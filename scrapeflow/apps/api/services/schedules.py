"""Schedule CRUD and dispatch-time job creation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from packages.core.errors import AppError, ErrorCode
from packages.core.models import (
    Job,
    JobKind,
    Organization,
    Schedule,
    ScheduleRun,
    ScheduleRunStatus,
)
from packages.core.schedules import next_run_after
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import AuthContext
from apps.api.schemas.automation import AutomationRequest
from apps.api.schemas.schedules import (
    ScheduleCreate,
    ScheduleRead,
    ScheduleRunRead,
    ScheduleUpdate,
    parse_schedule_template,
)
from apps.api.schemas.scrape import ScrapeRequest
from apps.api.services import jobs as job_service
from apps.api.services import quota as quota_service
from apps.api.services.audit import add_audit
from apps.api.services.automation import create_automation_job

_SCHEDULE_SCOPES = frozenset({"*"})


def schedule_read(schedule: Schedule) -> ScheduleRead:
    return ScheduleRead(
        id=schedule.id,
        name=schedule.name,
        kind=schedule.kind,
        cron=schedule.cron,
        timezone=schedule.timezone,
        enabled=schedule.enabled,
        template=schedule.template,
        watched_fields=list(schedule.watched_fields),
        notify_on_change=schedule.notify_on_change,
        next_run_at=schedule.next_run_at,
        last_run_at=schedule.last_run_at,
        last_job_id=schedule.last_job_id,
        last_error=schedule.last_error,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


def run_read(run: ScheduleRun) -> ScheduleRunRead:
    return ScheduleRunRead(
        id=run.id,
        schedule_id=run.schedule_id,
        job_id=run.job_id,
        trigger=run.trigger,
        status=run.status,
        scheduled_for=run.scheduled_for,
        credits=run.credits,
        error=run.error,
        values=run.values,
        changes=run.changes,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def schedule_context(schedule: Schedule, org: Organization) -> AuthContext:
    return AuthContext(
        org_id=schedule.org_id,
        user_id=schedule.created_by,
        api_key_id=None,
        role="owner",
        scopes=_SCHEDULE_SCOPES,
        auth_method="schedule",
        plan=org.plan.value,
    )


async def list_schedules(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Schedule], int]:
    total = (
        await db.execute(
            select(func.count()).select_from(Schedule).where(Schedule.org_id == org_id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(Schedule)
            .where(Schedule.org_id == org_id)
            .order_by(Schedule.created_at.desc(), Schedule.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(rows), int(total)


async def get_schedule(db: AsyncSession, *, org_id: uuid.UUID, schedule_id: uuid.UUID) -> Schedule:
    schedule = (
        await db.execute(
            select(Schedule).where(Schedule.id == schedule_id, Schedule.org_id == org_id)
        )
    ).scalar_one_or_none()
    if schedule is None:
        raise AppError(404, ErrorCode.NOT_FOUND, "Schedule not found")
    return schedule


async def create_schedule(
    db: AsyncSession,
    *,
    context: AuthContext,
    body: ScheduleCreate,
) -> Schedule:
    parsed = parse_schedule_template(body.kind, body.template)
    schedule = Schedule(
        org_id=context.org_id,
        created_by=context.user_id,
        name=body.name,
        kind=body.kind,
        cron=body.cron,
        timezone=body.timezone,
        enabled=body.enabled,
        template=parsed.model_dump(mode="json"),
        watched_fields=body.watched_fields,
        notify_on_change=body.notify_on_change,
        next_run_at=next_run_after(body.cron, body.timezone),
    )
    db.add(schedule)
    await db.flush()
    add_audit(
        db,
        action="schedule.created",
        resource_type="schedule",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(schedule.id),
        details={"kind": schedule.kind.value, "cron": schedule.cron, "timezone": schedule.timezone},
    )
    await db.commit()
    await db.refresh(schedule)
    return schedule


async def update_schedule(
    db: AsyncSession,
    *,
    context: AuthContext,
    schedule_id: uuid.UUID,
    body: ScheduleUpdate,
) -> Schedule:
    schedule = await get_schedule(db, org_id=context.org_id, schedule_id=schedule_id)
    if body.template is not None:
        parsed = parse_schedule_template(schedule.kind, body.template)
        schedule.template = parsed.model_dump(mode="json")
    if body.name is not None:
        schedule.name = body.name
    if body.cron is not None:
        schedule.cron = body.cron
    if body.timezone is not None:
        schedule.timezone = body.timezone
    if body.watched_fields is not None:
        schedule.watched_fields = body.watched_fields
    if body.notify_on_change is not None:
        schedule.notify_on_change = body.notify_on_change
    if body.cron is not None or body.timezone is not None:
        schedule.next_run_at = next_run_after(schedule.cron, schedule.timezone)
    if body.enabled is not None:
        schedule.enabled = body.enabled
        if body.enabled and schedule.next_run_at <= datetime.now(UTC):
            schedule.next_run_at = next_run_after(schedule.cron, schedule.timezone)
    add_audit(
        db,
        action="schedule.updated",
        resource_type="schedule",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(schedule.id),
        details={"enabled": schedule.enabled},
    )
    await db.commit()
    await db.refresh(schedule)
    return schedule


async def delete_schedule(
    db: AsyncSession,
    *,
    context: AuthContext,
    schedule_id: uuid.UUID,
) -> None:
    schedule = await get_schedule(db, org_id=context.org_id, schedule_id=schedule_id)
    await db.delete(schedule)
    add_audit(
        db,
        action="schedule.deleted",
        resource_type="schedule",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(schedule_id),
    )
    await db.commit()


async def list_runs(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    schedule_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ScheduleRun], int]:
    await get_schedule(db, org_id=org_id, schedule_id=schedule_id)
    total = (
        await db.execute(
            select(func.count())
            .select_from(ScheduleRun)
            .where(ScheduleRun.org_id == org_id, ScheduleRun.schedule_id == schedule_id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(ScheduleRun)
            .where(ScheduleRun.org_id == org_id, ScheduleRun.schedule_id == schedule_id)
            .order_by(ScheduleRun.created_at.desc(), ScheduleRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(rows), int(total)


async def create_job_for_schedule(
    db: AsyncSession,
    *,
    schedule: Schedule,
    org: Organization,
    settings: Settings,
    policy: SSRFPolicy,
    redis: Redis,
    run_key: str,
    request_id: str | None,
    commit: bool,
) -> tuple[Job, bool, quota_service.QuotaState]:
    context = schedule_context(schedule, org)
    if schedule.kind is JobKind.AUTOMATION:
        automation = AutomationRequest.model_validate(schedule.template)
        return await create_automation_job(
            db,
            context=context,
            request=automation,
            settings=settings,
            policy=policy,
            redis=redis,
            request_id=request_id,
            idempotency_key=run_key,
            schedule_id=schedule.id,
            commit=commit,
        )
    scrape = ScrapeRequest.model_validate(schedule.template)
    return await job_service.create_scrape_job(
        db,
        context=context,
        request=scrape,
        settings=settings,
        policy=policy,
        redis=redis,
        request_id=request_id,
        idempotency_key=run_key,
        schedule_id=schedule.id,
        commit=commit,
    )


async def run_now(
    db: AsyncSession,
    *,
    context: AuthContext,
    schedule_id: uuid.UUID,
    settings: Settings,
    policy: SSRFPolicy,
    redis: Redis,
) -> tuple[ScheduleRun, Job]:
    schedule = await get_schedule(db, org_id=context.org_id, schedule_id=schedule_id)
    schedule_pk = schedule.id
    org = await db.get(Organization, context.org_id)
    if org is None:  # pragma: no cover - authenticated org must exist
        raise AppError(404, ErrorCode.NOT_FOUND, "Organization not found")
    now = datetime.now(UTC)
    run_key = f"manual:{uuid.uuid4()}"
    run = ScheduleRun(
        org_id=context.org_id,
        schedule_id=schedule_pk,
        run_key=run_key,
        trigger="manual",
        status=ScheduleRunStatus.QUEUED,
        scheduled_for=now,
    )
    db.add(run)
    await db.flush()
    try:
        job, replay, _state = await create_job_for_schedule(
            db,
            schedule=schedule,
            org=org,
            settings=settings,
            policy=policy,
            redis=redis,
            run_key=run_key,
            request_id=f"schedule:{run.id}",
            commit=False,
        )
    except AppError as exc:
        await db.rollback()
        await record_skipped(
            db,
            schedule_id=schedule_pk,
            org_id=context.org_id,
            run_key=run_key,
            scheduled_for=now,
            trigger="manual",
            error=f"{exc.code.value}: {exc.message}",
        )
        raise
    stored_run = await db.get(ScheduleRun, run.id)
    if stored_run is None:  # pragma: no cover - flushed above
        raise AppError(500, ErrorCode.INTERNAL_ERROR, "Could not create schedule run")
    stored_run.job_id = job.id
    stored_run.credits = job.credits
    stored_run.status = ScheduleRunStatus.QUEUED
    schedule.last_run_at = now
    schedule.last_job_id = job.id
    schedule.last_error = None
    add_audit(
        db,
        action="schedule.run_now",
        resource_type="schedule",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(schedule.id),
        details={"job_id": str(job.id), "replay": replay, "credits": job.credits},
    )
    await db.commit()
    await db.refresh(stored_run)
    await db.refresh(job)
    return stored_run, job


async def record_skipped(
    db: AsyncSession,
    *,
    schedule_id: uuid.UUID,
    org_id: uuid.UUID,
    run_key: str,
    scheduled_for: datetime,
    trigger: str,
    error: str,
) -> None:
    """Record a skipped dispatch, updating the claimed run when one exists."""
    run = (
        await db.execute(select(ScheduleRun).where(ScheduleRun.run_key == run_key))
    ).scalar_one_or_none()
    if run is None:
        run = ScheduleRun(
            org_id=org_id,
            schedule_id=schedule_id,
            run_key=run_key,
            trigger=trigger,
            scheduled_for=scheduled_for,
        )
        db.add(run)
    run.status = ScheduleRunStatus.SKIPPED
    run.error = error[:2000]
    run.finished_at = datetime.now(UTC)
    schedule = await db.get(Schedule, schedule_id)
    if schedule is not None:
        schedule.last_error = error[:2000]
    await db.commit()
