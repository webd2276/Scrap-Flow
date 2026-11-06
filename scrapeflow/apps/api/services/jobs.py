"""Job creation, tenant-scoped reads, cancellation, and artifact lookups."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from packages.core.errors import AppError, ErrorCode
from packages.core.models import (
    TERMINAL_JOB_STATUSES,
    Artifact,
    Job,
    JobEvent,
    JobKind,
    JobStatus,
    Organization,
)
from packages.core.plans import plan_for, scrape_credit_cost
from packages.core.quota import settle_job_usage
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy, validate_url
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import AuthContext
from apps.api.schemas.scrape import (
    ArtifactRead,
    JobError,
    JobEventRead,
    JobRead,
    ScrapeRequest,
)
from apps.api.services import quota as quota_service
from apps.api.services.audit import add_audit
from apps.api.services.proxies import ensure_proxy_country


def ssrf_policy(settings: Settings) -> SSRFPolicy:
    return SSRFPolicy(allowed_ports=settings.egress_port_set)


async def create_scrape_job(
    db: AsyncSession,
    *,
    context: AuthContext,
    request: ScrapeRequest,
    settings: Settings,
    policy: SSRFPolicy,
    redis: Redis,
    request_id: str | None,
    idempotency_key: str | None,
    schedule_id: uuid.UUID | None = None,
    commit: bool = True,
) -> tuple[Job, bool, quota_service.QuotaState]:
    ensure_proxy_country(settings, request.proxy_country)
    if (
        request.timeout_seconds is not None
        and request.timeout_seconds > settings.job_timeout_seconds
    ):
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"timeout_seconds must not exceed {settings.job_timeout_seconds}",
        )

    target = await validate_url(request.url, policy)
    if request.webhook_url:
        webhook_target = await validate_url(request.webhook_url, policy)
        if webhook_target.scheme == "http":
            raise AppError(
                422,
                ErrorCode.VALIDATION_ERROR,
                "Webhook URLs must use HTTPS",
            )
        org = await db.get(Organization, context.org_id)
        if org is None or org.webhook_secret_encrypted is None:
            raise AppError(
                422,
                ErrorCode.VALIDATION_ERROR,
                "Configure a webhook signing secret before using webhook_url",
            )

    plan = plan_for(context.plan)
    if idempotency_key:
        existing = (
            await db.execute(
                select(Job).where(
                    Job.org_id == context.org_id,
                    Job.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            replay = await quota_service.replay_state(db, redis, org_id=context.org_id, plan=plan)
            return existing, True, replay

    max_pages = request.pagination.max_pages if request.pagination is not None else 1
    if max_pages > plan.max_pages:
        await quota_service.raise_plan_limit(
            db,
            redis,
            org_id=context.org_id,
            plan=plan,
            message=f"Your {plan.name} plan allows at most {plan.max_pages} pages per job",
        )

    cost = scrape_credit_cost(
        render_js=request.render_js,
        screenshot=request.screenshot,
        proxy_country=request.proxy_country,
        max_pages=max_pages,
    )
    job_id = uuid.uuid4()
    state = await quota_service.reserve_job(
        db,
        redis,
        settings=settings,
        org_id=context.org_id,
        job_id=job_id,
        plan=plan,
        cost=cost,
    )

    payload = request.model_dump(mode="json")
    payload["url"] = target.url
    job = Job(
        id=job_id,
        org_id=context.org_id,
        created_by=context.user_id,
        api_key_id=context.api_key_id,
        schedule_id=schedule_id,
        kind=JobKind.SCRAPE,
        status=JobStatus.QUEUED,
        url=target.url,
        payload=payload,
        credits=cost,
        idempotency_key=idempotency_key,
        request_id=request_id,
        max_attempts=settings.job_max_attempts,
    )
    try:
        db.add(job)
        quota_service.add_ledger_entry(
            db,
            state=state,
            org_id=context.org_id,
            job_id=job_id,
            credits=cost,
        )
        await db.flush()
        db.add(
            JobEvent(
                job_id=job.id,
                type="queued",
                message="Job accepted",
                data={"url": target.url, "render_js": request.render_js, "credits": cost},
            )
        )
        add_audit(
            db,
            action="job.created",
            resource_type="job",
            org_id=context.org_id,
            user_id=context.user_id,
            resource_id=str(job.id),
            details={
                "kind": job.kind.value,
                "render_js": request.render_js,
                "credits": cost,
            },
        )
        if commit:
            await db.commit()
    except IntegrityError:
        await db.rollback()
        await quota_service.release_reservation(
            redis,
            state=state,
            org_id=context.org_id,
            job_id=job_id,
            credits=cost,
        )
        if idempotency_key:
            existing = (
                await db.execute(
                    select(Job).where(
                        Job.org_id == context.org_id,
                        Job.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                replay = await quota_service.replay_state(
                    db, redis, org_id=context.org_id, plan=plan
                )
                return existing, True, replay
        raise
    except Exception:
        await db.rollback()
        await quota_service.release_reservation(
            redis,
            state=state,
            org_id=context.org_id,
            job_id=job_id,
            credits=cost,
        )
        raise
    if commit:
        await db.refresh(job)
    return job, False, state


async def list_jobs(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    status: JobStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Job], int]:
    conditions = [Job.org_id == org_id]
    if status is not None:
        conditions.append(Job.status == status)
    total = (
        await db.execute(select(func.count()).select_from(Job).where(*conditions))
    ).scalar_one()
    rows = (
        await db.execute(
            select(Job)
            .where(*conditions)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(rows), int(total)


async def get_job(db: AsyncSession, *, org_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = (
        await db.execute(select(Job).where(Job.id == job_id, Job.org_id == org_id))
    ).scalar_one_or_none()
    if job is None:
        raise AppError(404, ErrorCode.NOT_FOUND, "Job not found")
    return job


async def cancel_job(
    db: AsyncSession,
    *,
    context: AuthContext,
    job_id: uuid.UUID,
    redis: Redis,
) -> Job:
    job = await get_job(db, org_id=context.org_id, job_id=job_id)
    if job.status in TERMINAL_JOB_STATUSES:
        return job
    now = datetime.now(UTC)
    job.cancel_requested_at = now
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED
        job.finished_at = now
        job.duration_ms = 0
        message = "Job cancelled before execution"
    else:
        message = "Cancellation requested"
    db.add(
        JobEvent(
            job_id=job.id,
            type="cancel_requested",
            message=message,
        )
    )
    add_audit(
        db,
        action="job.cancel_requested",
        resource_type="job",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(job.id),
    )
    await db.commit()
    await db.refresh(job)
    if job.status in TERMINAL_JOB_STATUSES:
        await settle_job_usage(db, redis, job=job)
        await db.refresh(job)
    return job


async def list_events(db: AsyncSession, *, org_id: uuid.UUID, job_id: uuid.UUID) -> list[JobEvent]:
    await get_job(db, org_id=org_id, job_id=job_id)
    rows = (
        await db.execute(
            select(JobEvent)
            .where(JobEvent.job_id == job_id)
            .order_by(JobEvent.created_at, JobEvent.id)
        )
    ).scalars()
    return list(rows)


async def list_artifacts(
    db: AsyncSession, *, org_id: uuid.UUID, job_id: uuid.UUID
) -> list[Artifact]:
    await get_job(db, org_id=org_id, job_id=job_id)
    rows = (
        await db.execute(
            select(Artifact)
            .where(Artifact.org_id == org_id, Artifact.job_id == job_id)
            .order_by(Artifact.created_at, Artifact.id)
        )
    ).scalars()
    return list(rows)


async def get_artifact(db: AsyncSession, *, org_id: uuid.UUID, artifact_id: uuid.UUID) -> Artifact:
    artifact = (
        await db.execute(
            select(Artifact).where(
                Artifact.id == artifact_id,
                Artifact.org_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if artifact is None:
        raise AppError(404, ErrorCode.NOT_FOUND, "Artifact not found")
    return artifact


def job_read(job: Job) -> JobRead:
    error = None
    if job.error_code:
        error = JobError(
            code=job.error_code,
            message=job.error_message or job.error_code,
            details=job.error_details,
        )
    return JobRead(
        id=job.id,
        kind=job.kind,
        status=job.status,
        url=job.url,
        result=job.result,
        error=error,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        cancel_requested_at=job.cancel_requested_at,
        duration_ms=job.duration_ms,
    )


def event_read(event: JobEvent) -> JobEventRead:
    return JobEventRead(
        id=event.id,
        type=event.type,
        message=event.message,
        data=event.data,
        created_at=event.created_at,
    )


def artifact_read(artifact: Artifact) -> ArtifactRead:
    return ArtifactRead(
        id=artifact.id,
        job_id=artifact.job_id,
        kind=artifact.kind,
        filename=artifact.filename,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        expires_at=artifact.expires_at,
        created_at=artifact.created_at,
        download_url=f"/v1/artifacts/{artifact.id}/download",
    )
