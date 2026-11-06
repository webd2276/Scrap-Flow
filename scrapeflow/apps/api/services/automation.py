"""Automation job acceptance and secret staging."""

from __future__ import annotations

import contextlib
import uuid

from packages.core.errors import AppError, ErrorCode
from packages.core.models import Job, JobEvent, JobKind, JobStatus, Organization
from packages.core.plans import automation_credit_cost, plan_for
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy, validate_url
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import AuthContext
from apps.api.schemas.automation import (
    AutomationRequest,
    AutomationStep,
    GotoStep,
    LoopPagesStep,
    ScreenshotStep,
    walk_steps,
)
from apps.api.services import quota as quota_service
from apps.api.services.audit import add_audit
from apps.api.services.proxies import ensure_proxy_country
from apps.api.services.secrets import delete_secrets, store_secrets


async def _validate_request(
    request: AutomationRequest,
    *,
    settings: Settings,
    policy: SSRFPolicy,
) -> tuple[str, list[tuple[AutomationStep, int]]]:
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

    walked = walk_steps(request.steps)
    if len(walked) > settings.automation_max_steps:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"At most {settings.automation_max_steps} steps are allowed",
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
    return target.url, walked


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
    schedule_id: uuid.UUID | None = None,
    commit: bool = True,
) -> tuple[Job, bool, quota_service.QuotaState]:
    target_url, walked = await _validate_request(request, settings=settings, policy=policy)
    if request.webhook_url:
        org = await db.get(Organization, context.org_id)
        if org is None or org.webhook_secret_encrypted is None:
            raise AppError(
                422,
                ErrorCode.VALIDATION_ERROR,
                "Configure a webhook signing secret before using webhook_url",
            )
    plan = plan_for(context.plan)

    if idempotency_key:
        existing = await _existing_job(db, org_id=context.org_id, idempotency_key=idempotency_key)
        if existing is not None:
            replay = await quota_service.replay_state(db, redis, org_id=context.org_id, plan=plan)
            return existing, True, replay

    if len(walked) > plan.max_steps:
        await quota_service.raise_plan_limit(
            db,
            redis,
            org_id=context.org_id,
            plan=plan,
            message=f"Your {plan.name} plan allows at most {plan.max_steps} steps per job",
        )
    loop_steps = [step for step, _depth in walked if isinstance(step, LoopPagesStep)]
    page_demand = sum(step.max_pages for step in loop_steps) or 1
    if page_demand > plan.max_pages:
        await quota_service.raise_plan_limit(
            db,
            redis,
            org_id=context.org_id,
            plan=plan,
            message=f"Your {plan.name} plan allows at most {plan.max_pages} pages per job",
        )

    cost = automation_credit_cost(
        step_count=len(walked),
        screenshot=request.screenshot,
        screenshot_steps=sum(1 for step, _depth in walked if isinstance(step, ScreenshotStep)),
        proxy_country=request.proxy_country,
        extra_pages=sum(max(0, step.max_pages - 1) for step in loop_steps),
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

    payload = request.model_dump(mode="json", exclude={"secrets"})
    payload["url"] = target_url
    job = Job(
        id=job_id,
        org_id=context.org_id,
        created_by=context.user_id,
        api_key_id=context.api_key_id,
        schedule_id=schedule_id,
        kind=JobKind.AUTOMATION,
        status=JobStatus.QUEUED,
        url=target_url,
        payload=payload,
        credits=cost,
        idempotency_key=idempotency_key,
        request_id=request_id,
        max_attempts=settings.job_max_attempts,
    )

    try:
        await store_secrets(redis, settings, job_id, request.secrets)
    except Exception as exc:
        await db.rollback()
        await quota_service.release_reservation(
            redis,
            state=state,
            org_id=context.org_id,
            job_id=job_id,
            credits=cost,
        )
        raise AppError(
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "Secret staging is unavailable; retry the request",
        ) from exc

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
                job_id=job_id,
                type="queued",
                message="Automation job accepted",
                data={
                    "url": target_url,
                    "steps": len(walked),
                    "secrets": len(request.secrets),
                    "credits": cost,
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
                "steps": len(walked),
                "secret_count": len(request.secrets),
                "credits": cost,
            },
        )
        if commit:
            await db.commit()
    except IntegrityError:
        await db.rollback()
        await _discard_secrets(redis, job_id)
        await quota_service.release_reservation(
            redis,
            state=state,
            org_id=context.org_id,
            job_id=job_id,
            credits=cost,
        )
        if idempotency_key:
            existing = await _existing_job(
                db, org_id=context.org_id, idempotency_key=idempotency_key
            )
            if existing is not None:
                replay = await quota_service.replay_state(
                    db, redis, org_id=context.org_id, plan=plan
                )
                return existing, True, replay
        raise
    except Exception:
        await db.rollback()
        await _discard_secrets(redis, job_id)
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


async def _discard_secrets(redis: Redis, job_id: uuid.UUID) -> None:
    # The TTL bounds the exposure window; a failed cleanup must not mask the
    # original database error.
    with contextlib.suppress(Exception):
        await delete_secrets(redis, job_id)
