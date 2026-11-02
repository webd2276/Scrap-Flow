"""Job reads, cancellation, events, and artifact download."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from packages.core.artifacts import ArtifactStore, ArtifactStoreError
from packages.core.db import get_db
from packages.core.errors import AppError, ErrorCode
from packages.core.models import JobStatus
from packages.core.redis import get_redis
from packages.core.scopes import Scope
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import AuthContext, org_rate_limit, require_any_scope, require_scope
from apps.api.schemas.scrape import (
    ArtifactRead,
    JobAccepted,
    JobEventRead,
    JobList,
    JobRead,
)
from apps.api.services import jobs as job_service

router = APIRouter(tags=["jobs"])


@router.get("/v1/jobs", response_model=JobList)
async def list_jobs(
    response: Response,
    status: JobStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    context: AuthContext = Depends(require_scope(Scope.JOBS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> JobList:
    jobs, total = await job_service.list_jobs(
        db, org_id=context.org_id, status=status, limit=limit, offset=offset
    )
    return JobList(
        items=[job_service.job_read(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/v1/jobs/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.JOBS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> JobRead:
    job = await job_service.get_job(db, org_id=context.org_id, job_id=job_id)
    return job_service.job_read(job)


@router.post("/v1/jobs/{job_id}/cancel", response_model=JobAccepted)
async def cancel_job(
    job_id: uuid.UUID,
    response: Response,
    context: AuthContext = Depends(require_any_scope(Scope.SCRAPE_WRITE, Scope.AUTOMATION_WRITE)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _: None = Depends(org_rate_limit),
) -> JobAccepted:
    job = await job_service.cancel_job(db, context=context, job_id=job_id, redis=redis)
    return JobAccepted(job=job_service.job_read(job))


@router.get("/v1/jobs/{job_id}/events", response_model=list[JobEventRead])
async def list_events(
    job_id: uuid.UUID,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.JOBS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> list[JobEventRead]:
    events = await job_service.list_events(db, org_id=context.org_id, job_id=job_id)
    return [job_service.event_read(event) for event in events]


@router.get("/v1/jobs/{job_id}/artifacts", response_model=list[ArtifactRead])
async def list_artifacts(
    job_id: uuid.UUID,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.JOBS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> list[ArtifactRead]:
    artifacts = await job_service.list_artifacts(db, org_id=context.org_id, job_id=job_id)
    return [job_service.artifact_read(artifact) for artifact in artifacts]


@router.get("/v1/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: uuid.UUID,
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.JOBS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> Response:
    artifact = await job_service.get_artifact(db, org_id=context.org_id, artifact_id=artifact_id)
    if artifact.expires_at is not None and artifact.expires_at <= datetime.now(UTC):
        raise AppError(404, ErrorCode.NOT_FOUND, "Artifact expired")
    store: ArtifactStore = request.app.state.artifact_store
    presigned = store.presigned_url(artifact.storage_key)
    if presigned is not None:
        return RedirectResponse(presigned, status_code=307)
    try:
        content = store.get(artifact.storage_key)
    except ArtifactStoreError as exc:
        raise AppError(503, ErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc
    headers = {
        "Content-Disposition": f'attachment; filename="{artifact.filename}"',
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Cache-Control": "private, max-age=60",
    }
    return Response(
        content=content,
        media_type=artifact.content_type,
        headers=headers,
    )
