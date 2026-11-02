"""Automation submission endpoint."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from packages.core.db import get_db
from packages.core.errors import AppError, ErrorCode
from packages.core.redis import get_redis
from packages.core.scopes import Scope
from packages.core.settings import Settings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import (
    AuthContext,
    get_app_settings,
    org_rate_limit,
    require_scope,
)
from apps.api.middleware.request_context import current_request_id
from apps.api.schemas.automation import AutomationRequest
from apps.api.schemas.scrape import JobAccepted
from apps.api.services import automation as automation_service
from apps.api.services import jobs as job_service

router = APIRouter(prefix="/v1/automate", tags=["automation"])

_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_IDEMPOTENCY_KEY = Annotated[str | None, Header(alias="Idempotency-Key")]


async def idempotency_key(value: _IDEMPOTENCY_KEY = None) -> str | None:
    if value is None:
        return None
    if not _IDEMPOTENCY.fullmatch(value):
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Idempotency-Key must match [A-Za-z0-9._:-]{1,128}",
        )
    return value


@router.post("", response_model=JobAccepted, status_code=202)
async def submit_automation(
    body: AutomationRequest,
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.AUTOMATION_WRITE)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
    idempotency: str | None = Depends(idempotency_key),
    _: None = Depends(org_rate_limit),
) -> JobAccepted:
    job, replay, quota = await automation_service.create_automation_job(
        db,
        context=context,
        request=body,
        settings=settings,
        policy=request.app.state.ssrf_policy,
        redis=redis,
        request_id=current_request_id() or None,
        idempotency_key=idempotency,
    )
    response.headers.update(quota.headers())
    if replay:
        response.status_code = 200
        response.headers["Idempotent-Replay"] = "true"
    else:
        request.app.state.dispatcher.enqueue(job.id)
    return JobAccepted(job=job_service.job_read(job), deduplicated=replay)
