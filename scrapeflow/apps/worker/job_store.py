"""Durable job persistence used by the worker and reaper."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from packages.core.db import create_engine, create_sessionmaker
from packages.core.models import Artifact, Job, JobEvent, JobStatus
from packages.core.observability import record_job_completion
from packages.core.settings import Settings
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_TERMINAL_STATUSES = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.TIMED_OUT}
)


def sessionmaker(settings: Settings) -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _sessionmaker is None:
        _engine = create_engine(settings)
        _sessionmaker = create_sessionmaker(_engine)
    return _sessionmaker


async def dispose() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def add_event(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    event_type: str,
    message: str | None = None,
    data: dict[str, object] | None = None,
) -> None:
    session.add(
        JobEvent(
            job_id=job_id,
            type=event_type,
            message=message,
            data=data or {},
        )
    )


async def claim_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    settings: Settings,
) -> Job | None:
    now = datetime.now(UTC)
    statement = (
        update(Job)
        .where(
            Job.id == job_id,
            Job.status == JobStatus.QUEUED,
            Job.attempts < Job.max_attempts,
        )
        .values(
            status=JobStatus.RUNNING,
            attempts=Job.attempts + 1,
            worker_id=worker_id,
            started_at=func.coalesce(Job.started_at, now),
            lease_expires_at=now + timedelta(seconds=settings.job_lease_seconds),
            error_code=None,
            error_message=None,
            error_details=None,
        )
        .returning(Job)
        .execution_options(synchronize_session=False)
    )
    job = (await session.execute(statement)).scalar_one_or_none()
    if job is None:
        await session.rollback()
        return None
    add_event(
        session,
        job_id=job.id,
        event_type="started",
        message="Worker claimed the job",
        data={"attempt": job.attempts, "worker_id": worker_id},
    )
    await session.commit()
    await session.refresh(job)
    return job


async def cancel_requested(session: AsyncSession, job_id: uuid.UUID) -> bool:
    value = (
        await session.execute(select(Job.cancel_requested_at).where(Job.id == job_id))
    ).scalar_one_or_none()
    return value is not None


async def heartbeat(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    settings: Settings,
) -> None:
    await session.execute(
        update(Job)
        .where(
            Job.id == job_id,
            Job.status == JobStatus.RUNNING,
            Job.worker_id == worker_id,
        )
        .values(lease_expires_at=datetime.now(UTC) + timedelta(seconds=settings.job_lease_seconds))
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def finish_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    status: JobStatus,
    result: dict[str, object] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    error_details: dict[str, object] | None = None,
    event_message: str | None = None,
) -> Job | None:
    job = await session.get(Job, job_id)
    if job is None:
        return None
    previous_status = job.status
    now = datetime.now(UTC)
    job.status = status
    job.result = result
    job.error_code = error_code
    job.error_message = error_message
    job.error_details = error_details
    job.finished_at = now
    job.lease_expires_at = None
    job.worker_id = None
    if job.started_at is not None:
        job.duration_ms = int((now - job.started_at).total_seconds() * 1000)
    add_event(
        session,
        job_id=job.id,
        event_type=status.value,
        message=event_message or status.value.replace("_", " ").capitalize(),
        data={"error_code": error_code} if error_code else None,
    )
    await session.commit()
    await session.refresh(job)
    if previous_status not in _TERMINAL_STATUSES:
        record_job_completion(
            kind=job.kind.value,
            status=job.status.value,
            duration_seconds=(job.duration_ms / 1000.0 if job.duration_ms is not None else None),
            error_code=job.error_code,
        )
    return job


async def add_artifact(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    kind: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    storage_key: str,
    expires_at: datetime | None,
) -> Artifact:
    artifact = Artifact(
        org_id=org_id,
        job_id=job_id,
        kind=kind,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        storage_key=storage_key,
        expires_at=expires_at,
    )
    session.add(artifact)
    await session.commit()
    await session.refresh(artifact)
    return artifact


async def expired_running_jobs(
    session: AsyncSession, *, now: datetime, limit: int = 100
) -> Sequence[Job]:
    rows = (
        await session.execute(
            select(Job)
            .where(
                Job.status == JobStatus.RUNNING,
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at < now,
            )
            .order_by(Job.lease_expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).scalars()
    return list(rows)


async def stale_queued_jobs(
    session: AsyncSession, *, now: datetime, older_than_seconds: int, limit: int = 100
) -> Sequence[Job]:
    threshold = now - timedelta(seconds=older_than_seconds)
    rows = (
        await session.execute(
            select(Job)
            .where(
                Job.status == JobStatus.QUEUED,
                Job.created_at < threshold,
                Job.attempts < Job.max_attempts,
            )
            .order_by(Job.created_at)
            .limit(limit)
        )
    ).scalars()
    return list(rows)


async def terminal_job_ids(session: AsyncSession, *, job_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not job_ids:
        return set()
    rows = (
        await session.execute(
            select(Job.id).where(
                Job.id.in_(job_ids),
                Job.status.in_(
                    [
                        JobStatus.SUCCEEDED,
                        JobStatus.FAILED,
                        JobStatus.CANCELLED,
                        JobStatus.TIMED_OUT,
                    ]
                ),
            )
        )
    ).scalars()
    return set(rows)
