"""Billing catalog, usage, Stripe checkout/portal, and webhooks."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from packages.core.db import get_db
from packages.core.errors import AppError, ErrorCode
from packages.core.models import Organization, OrgPlan
from packages.core.plans import PLANS, plan_for
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
from apps.api.schemas.billing import (
    CheckoutRequest,
    CheckoutResponse,
    PlanRead,
    PortalRequest,
    UsageRead,
    WebhookResponse,
)
from apps.api.services import quota as quota_service
from apps.api.services.audit import add_audit
from apps.api.services.billing import BillingService

router = APIRouter(prefix="/v1/billing", tags=["billing"])

_MAX_WEBHOOK_BYTES = 1_000_000


def _plan_read(code: str | OrgPlan) -> PlanRead:
    plan = plan_for(code)
    return PlanRead(
        code=plan.code,
        name=plan.name,
        monthly_credits=plan.monthly_credits,
        max_concurrency=plan.max_concurrency,
        max_steps=plan.max_steps,
        max_pages=plan.max_pages,
        artifact_retention_days=plan.artifact_retention_days,
    )


@router.get("/plans", response_model=list[PlanRead])
async def list_plans() -> list[PlanRead]:
    return [_plan_read(code) for code in PLANS]


@router.get("/usage", response_model=UsageRead)
async def usage(
    context: AuthContext = Depends(require_scope(Scope.BILLING_MANAGE)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
    _: None = Depends(org_rate_limit),
) -> UsageRead:
    plan = plan_for(context.plan)
    summary = await quota_service.usage_summary(db, redis, org_id=context.org_id, plan=plan)
    return UsageRead(
        plan=plan.code,
        plan_name=plan.name,
        period=str(summary["period"]),
        monthly_credits=plan.monthly_credits,
        used=int(summary["used"]),
        remaining=int(summary["remaining"]),
        reset_seconds=int(summary["reset_seconds"]),
        max_concurrency=plan.max_concurrency,
        max_steps=plan.max_steps,
        max_pages=plan.max_pages,
        artifact_retention_days=plan.artifact_retention_days,
        billing_enabled=settings.billing_enabled,
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    body: CheckoutRequest,
    context: AuthContext = Depends(require_scope(Scope.BILLING_MANAGE)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    _: None = Depends(org_rate_limit),
) -> CheckoutResponse:
    service = BillingService(settings)
    service.require_enabled()
    org = await db.get(Organization, context.org_id)
    if org is None:  # pragma: no cover - authenticated context implies it
        raise AppError(404, ErrorCode.NOT_FOUND, "Organization not found")
    plan = plan_for(body.plan)
    success_url = (
        body.success_url
        or settings.billing_success_url
        or f"{settings.public_base_url}/billing/success"
    )
    cancel_url = (
        body.cancel_url
        or settings.billing_cancel_url
        or f"{settings.public_base_url}/billing/cancel"
    )
    url = await service.create_checkout(
        db,
        org=org,
        plan=plan,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    add_audit(
        db,
        action="billing.checkout_started",
        resource_type="organization",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(context.org_id),
        details={"plan": plan.code.value},
    )
    await db.commit()
    return CheckoutResponse(url=url)


@router.post("/portal", response_model=CheckoutResponse)
async def portal(
    body: PortalRequest,
    context: AuthContext = Depends(require_scope(Scope.BILLING_MANAGE)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    _: None = Depends(org_rate_limit),
) -> CheckoutResponse:
    service = BillingService(settings)
    service.require_enabled()
    org = await db.get(Organization, context.org_id)
    if org is None:  # pragma: no cover
        raise AppError(404, ErrorCode.NOT_FOUND, "Organization not found")
    return_url = (
        body.return_url
        or settings.billing_portal_return_url
        or f"{settings.public_base_url}/billing"
    )
    url = await service.create_portal(org=org, return_url=return_url)
    add_audit(
        db,
        action="billing.portal_opened",
        resource_type="organization",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(context.org_id),
    )
    await db.commit()
    return CheckoutResponse(url=url)


@router.post("/webhook", response_model=WebhookResponse)
async def stripe_webhook(
    request: Request,
    signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> WebhookResponse:
    service = BillingService(settings)
    service.require_enabled()
    payload = await request.body()
    if len(payload) > _MAX_WEBHOOK_BYTES:
        raise AppError(413, ErrorCode.BILLING_ERROR, "Webhook payload is too large")
    event = service.verify_and_parse(payload, signature)
    duplicate = await service.handle_event(db, event=event)
    return WebhookResponse(duplicate=duplicate)
