"""Schedule CRUD, manual runs, and run history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status
from packages.core.db import get_db
from packages.core.redis import get_redis
from packages.core.scopes import Scope
from packages.core.settings import Settings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import AuthContext, get_app_settings, org_rate_limit, require_scope
from apps.api.schemas.schedules import (
    ScheduleCreate,
    ScheduleList,
    ScheduleRead,
    ScheduleRunList,
    ScheduleRunNowResponse,
    ScheduleUpdate,
)
from apps.api.services import jobs as job_service
from apps.api.services import schedules as schedule_service

router = APIRouter(prefix="/v1/schedules", tags=["schedules"])


@router.post("", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.SCHEDULES_WRITE)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> ScheduleRead:
    schedule = await schedule_service.create_schedule(db, context=context, body=body)
    return schedule_service.schedule_read(schedule)


@router.get("", response_model=ScheduleList)
async def list_schedules(
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    context: AuthContext = Depends(require_scope(Scope.JOBS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> ScheduleList:
    schedules, total = await schedule_service.list_schedules(
        db, org_id=context.org_id, limit=limit, offset=offset
    )
    return ScheduleList(
        items=[schedule_service.schedule_read(item) for item in schedules],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{schedule_id}", response_model=ScheduleRead)
async def get_schedule(
    schedule_id: uuid.UUID,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.JOBS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> ScheduleRead:
    schedule = await schedule_service.get_schedule(
        db, org_id=context.org_id, schedule_id=schedule_id
    )
    return schedule_service.schedule_read(schedule)


@router.patch("/{schedule_id}", response_model=ScheduleRead)
async def update_schedule(
    schedule_id: uuid.UUID,
    body: ScheduleUpdate,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.SCHEDULES_WRITE)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> ScheduleRead:
    schedule = await schedule_service.update_schedule(
        db, context=context, schedule_id=schedule_id, body=body
    )
    return schedule_service.schedule_read(schedule)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: uuid.UUID,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.SCHEDULES_WRITE)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> Response:
    await schedule_service.delete_schedule(db, context=context, schedule_id=schedule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{schedule_id}/run", response_model=ScheduleRunNowResponse)
async def run_schedule_now(
    schedule_id: uuid.UUID,
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.SCHEDULES_WRITE)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
    _: None = Depends(org_rate_limit),
) -> ScheduleRunNowResponse:
    run, job = await schedule_service.run_now(
        db,
        context=context,
        schedule_id=schedule_id,
        settings=settings,
        policy=request.app.state.ssrf_policy,
        redis=redis,
    )
    request.app.state.dispatcher.enqueue(job.id)
    return ScheduleRunNowResponse(
        run=schedule_service.run_read(run),
        job=job_service.job_read(job),
    )


@router.get("/{schedule_id}/runs", response_model=ScheduleRunList)
async def list_schedule_runs(
    schedule_id: uuid.UUID,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    context: AuthContext = Depends(require_scope(Scope.JOBS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> ScheduleRunList:
    runs, total = await schedule_service.list_runs(
        db,
        org_id=context.org_id,
        schedule_id=schedule_id,
        limit=limit,
        offset=offset,
    )
    return ScheduleRunList(
        items=[schedule_service.run_read(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{schedule_id}/history", response_model=ScheduleRunList)
async def schedule_history(
    schedule_id: uuid.UUID,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    context: AuthContext = Depends(require_scope(Scope.JOBS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> ScheduleRunList:
    runs, total = await schedule_service.list_runs(
        db,
        org_id=context.org_id,
        schedule_id=schedule_id,
        limit=limit,
        offset=offset,
    )
    return ScheduleRunList(
        items=[schedule_service.run_read(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )
