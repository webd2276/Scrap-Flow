"""Streaming job and schedule-history exports."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from packages.core.db import get_db
from packages.core.exporting import (
    content_disposition,
    csv_chunk,
    flatten_mapping,
    iter_json,
)
from packages.core.models import Job, ScheduleRun
from packages.core.scopes import Scope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import AuthContext, org_rate_limit, require_scope
from apps.api.services import jobs as job_service
from apps.api.services import schedules as schedule_service

router = APIRouter(tags=["exports"])

ExportFormat = Literal["csv", "json"]

_JOB_HEADER = [
    "id",
    "kind",
    "status",
    "url",
    "error_code",
    "error_message",
    "attempts",
    "max_attempts",
    "credits",
    "created_at",
    "started_at",
    "finished_at",
    "duration_ms",
]
_SCHEDULE_HEADER = [
    "run_id",
    "job_id",
    "trigger",
    "status",
    "scheduled_for",
    "created_at",
    "finished_at",
    "credits",
    "error",
    "values",
    "changes",
]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _job_row(job: Job) -> list[Any]:
    return [
        str(job.id),
        job.kind.value,
        job.status.value,
        job.url,
        job.error_code,
        job.error_message,
        job.attempts,
        job.max_attempts,
        job.credits,
        _iso(job.created_at),
        _iso(job.started_at),
        _iso(job.finished_at),
        job.duration_ms,
    ]


def _job_payload(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "kind": job.kind.value,
        "status": job.status.value,
        "url": job.url,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "credits": job.credits,
        "created_at": _iso(job.created_at),
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "duration_ms": job.duration_ms,
        "result": job.result,
    }


def _run_payload(run: ScheduleRun) -> dict[str, Any]:
    return {
        "run_id": str(run.id),
        "job_id": str(run.job_id) if run.job_id else None,
        "trigger": run.trigger,
        "status": run.status.value,
        "scheduled_for": _iso(run.scheduled_for),
        "created_at": _iso(run.created_at),
        "finished_at": _iso(run.finished_at),
        "credits": run.credits,
        "error": run.error,
        "values": run.values,
        "changes": run.changes,
    }


def _run_row(run: ScheduleRun) -> list[Any]:
    return [
        str(run.id),
        str(run.job_id) if run.job_id else None,
        run.trigger,
        run.status.value,
        _iso(run.scheduled_for),
        _iso(run.created_at),
        _iso(run.finished_at),
        run.credits,
        run.error,
        json.dumps(run.values, separators=(",", ":"), sort_keys=True) if run.values else None,
        json.dumps(run.changes, separators=(",", ":"), sort_keys=True) if run.changes else None,
    ]


def _export_headers(filename: str) -> dict[str, str]:
    return {
        "Content-Disposition": content_disposition(filename),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }


@router.get("/v1/jobs/{job_id}/export")
async def export_job(
    job_id: uuid.UUID,
    response: Response,
    format: ExportFormat = Query(default="json"),
    context: AuthContext = Depends(require_scope(Scope.EXPORTS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> StreamingResponse:
    job = await job_service.get_job(db, org_id=context.org_id, job_id=job_id)
    filename = f"job-{job.id}.{format}"
    if format == "json":
        body: AsyncIterator[bytes] = _sync_iterator(iter_json(_job_payload(job)))
        media_type = "application/json"
    else:
        flattened = flatten_mapping(job.result if job.result is not None else {}, "result")
        keys = sorted(flattened)
        header = [*_JOB_HEADER, *keys]

        async def rows() -> AsyncIterator[bytes]:
            yield csv_chunk(header)
            yield csv_chunk([*_job_row(job), *(flattened[key] for key in keys)])

        body = rows()
        media_type = "text/csv; charset=utf-8"
    return StreamingResponse(
        body,
        media_type=media_type,
        headers=_export_headers(filename),
    )


@router.get("/v1/schedules/{schedule_id}/export")
async def export_schedule(
    schedule_id: uuid.UUID,
    response: Response,
    format: ExportFormat = Query(default="json"),
    context: AuthContext = Depends(require_scope(Scope.EXPORTS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> StreamingResponse:
    schedule = await schedule_service.get_schedule(
        db, org_id=context.org_id, schedule_id=schedule_id
    )
    filename = f"schedule-{schedule.id}.{format}"
    query = (
        select(ScheduleRun)
        .where(
            ScheduleRun.org_id == context.org_id,
            ScheduleRun.schedule_id == schedule.id,
        )
        .order_by(ScheduleRun.created_at, ScheduleRun.id)
    )

    if format == "json":

        async def json_body() -> AsyncIterator[bytes]:
            yield b"["
            first = True
            result = await db.stream(query)
            async for run in result.scalars():
                if not first:
                    yield b","
                first = False
                for chunk in iter_json(_run_payload(run)):
                    yield chunk
            yield b"]"

        body = json_body()
        media_type = "application/json"
    else:

        async def csv_body() -> AsyncIterator[bytes]:
            yield csv_chunk(_SCHEDULE_HEADER)
            result = await db.stream(query)
            async for run in result.scalars():
                yield csv_chunk(_run_row(run))

        body = csv_body()
        media_type = "text/csv; charset=utf-8"
    return StreamingResponse(
        body,
        media_type=media_type,
        headers=_export_headers(filename),
    )


async def _sync_iterator(source: Any) -> AsyncIterator[bytes]:
    for chunk in source:
        yield chunk
