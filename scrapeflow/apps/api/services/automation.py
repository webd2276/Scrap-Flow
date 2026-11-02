"""Automation job acceptance and secret staging."""

from __future__ import annotations

import contextlib
import uuid

from packages.core.errors import AppError, ErrorCode
from packages.core.models import Job, JobEvent, JobKind, JobStatus
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy, validate_url
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import AuthContext
from apps.api.schemas.automation import (
    AutomationRequest,
    GotoStep,
    walk_steps,
)
from apps.api.services.audit import add_audit
from apps.api.services.secrets import delete_secrets, store_secrets


async def _validate_request(
    request: AutomationRequest,
    *,
    settings: Settings,
    policy: SSRFPolicy,
) -> str:
    if request.proxy_country is not None:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"Proxy country {request.proxy_country} is not available",
        )
    if (
        request.timeout_seconds is not None
        and request.timeout_seconds > settings.job_timeout_seconds
    ):
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"timeout_seconds must not exceed {settings.job_timeout_seconds}",
        )

    walked = walk_steps(request.steps)
    if len(walked) > settings.automation_max_steps:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"This plan allows at most {settings.automation_max_steps} steps",
        )
    deepest = max(depth for _step, depth in walked)
    if deepest > settings.automation_max_depth:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"Steps may be nested at most {settings.automation_max_depth} levels",
        )

    if len(request.secrets) > 20:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "At most 20 secrets are allowed",
        )
    secret_bytes = sum(len(value.encode("utf-8")) for value in request.secrets.values())
    if secret_bytes > settings.automation_max_secret_bytes:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"Secret values exceed the {settings.automation_max_secret_bytes} byte limit",
        )

    target = await validate_url(request.url, policy)
    for step, _depth in walked:
        if isinstance(step, GotoStep):
            await validate_url(step.url, policy)

    if request.webhook_url:
        webhook_target = await validate_url(request.webhook_url, policy)
        if webhook_target.scheme == "http":
            raise AppError(
                422,
                ErrorCode.VALIDATION_ERROR,
                "Webhook URLs must use HTTPS",
            )
    return target.url


async def _existing_job(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    idempotency_key: str,
) -> Job | None:
    return (
        await db.execute(
            select(Job).where(
                Job.org_id == org_id,
                Job.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()


async def create_automation_job(
    db: AsyncSession,
    *,
    context: AuthContext,
    request: AutomationRequest,
    settings: Settings,
    policy: SSRFPolicy,
    redis: Redis,
    request_id: str | None,
    idempotency_key: str | None,
) -> tuple[Job, bool]:
    target_url = await _validate_request(request, settings=settings, policy=policy)

    if idempotency_key:
        existing = await _existing_job(db, org_id=context.org_id, idempotency_key=idempotency_key)
        if existing is not None:
            return existing, True

    job_id = uuid.uuid4()
    payload = request.model_dump(mode="json", exclude={"secrets"})
    payload["url"] = target_url
    job = Job(
        id=job_id,
        org_id=context.org_id,
        created_by=context.user_id,
        api_key_id=context.api_key_id,
        kind=JobKind.AUTOMATION,
        status=JobStatus.QUEUED,
        url=target_url,
        payload=payload,
        idempotency_key=idempotency_key,
        request_id=request_id,
        max_attempts=settings.job_max_attempts,
    )

    try:
        await store_secrets(redis, settings, job_id, request.secrets)
    except Exception as exc:
        raise AppError(
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "Secret staging is unavailable; retry the request",
        ) from exc

    db.add(job)
    try:
        await db.flush()
        db.add(
            JobEvent(
                job_id=job_id,
                type="queued",
                message="Automation job accepted",
                data={
                    "url": target_url,
                    "steps": len(walk_steps(request.steps)),
                    "secrets": len(request.secrets),
                },
            )
        )
        add_audit(
            db,
            action="job.created",
            resource_type="job",
            org_id=context.org_id,
            user_id=context.user_id,
            resource_id=str(job_id),
            details={
                "kind": JobKind.AUTOMATION.value,
                "steps": len(walk_steps(request.steps)),
                "secret_count": len(request.secrets),
            },
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        await _discard_secrets(redis, job_id)
        if idempotency_key:
            existing = await _existing_job(
                db, org_id=context.org_id, idempotency_key=idempotency_key
            )
            if existing is not None:
                return existing, True
        raise
    except Exception:
        await db.rollback()
        await _discard_secrets(redis, job_id)
        raise

    await db.refresh(job)
    return job, False


async def _discard_secrets(redis: Redis, job_id: uuid.UUID) -> None:
    # The TTL bounds the exposure window; a failed cleanup must not mask the
    # original database error.
    with contextlib.suppress(Exception):
        await delete_secrets(redis, job_id)
