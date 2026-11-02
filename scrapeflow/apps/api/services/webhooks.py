"""Webhook endpoint management and signing-secret lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from packages.core.errors import AppError, ErrorCode
from packages.core.models import Organization, WebhookDelivery, WebhookEndpoint
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy, validate_url
from packages.core.webhooks import generate_secret, seal_secret
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import AuthContext
from apps.api.schemas.webhooks import (
    WebhookDeliveryRead,
    WebhookEndpointCreate,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
)
from apps.api.services.audit import add_audit

# Every terminal job fans out to each subscribed endpoint, so an unbounded
# registry would let one org multiply delivery work and outbox growth.
MAX_ENDPOINTS_PER_ORG = 20


async def _validate_webhook_url(url: str, policy: SSRFPolicy) -> str:
    target = await validate_url(url, policy)
    if target.scheme != "https":
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Webhook URLs must use HTTPS",
        )
    return target.url


def endpoint_read(endpoint: WebhookEndpoint, *, has_secret: bool) -> WebhookEndpointRead:
    return WebhookEndpointRead(
        id=endpoint.id,
        url=endpoint.url,
        description=endpoint.description,
        events=list(endpoint.events),
        enabled=endpoint.enabled,
        has_secret=has_secret,
        last_success_at=endpoint.last_success_at,
        last_failure_at=endpoint.last_failure_at,
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
    )


def delivery_read(delivery: WebhookDelivery) -> WebhookDeliveryRead:
    return WebhookDeliveryRead(
        id=delivery.id,
        endpoint_id=delivery.endpoint_id,
        url=delivery.url,
        event_type=delivery.event_type,
        status=delivery.status,
        attempts=delivery.attempts,
        max_attempts=delivery.max_attempts,
        next_attempt_at=delivery.next_attempt_at,
        response_status=delivery.response_status,
        response_body=delivery.response_body,
        error=delivery.error,
        payload=delivery.payload,
        created_at=delivery.created_at,
        delivered_at=delivery.delivered_at,
    )


async def _org(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Organization:
    if for_update:
        org = (
            await db.execute(
                select(Organization).where(Organization.id == org_id).with_for_update()
            )
        ).scalar_one_or_none()
    else:
        org = await db.get(Organization, org_id)
    if org is None:  # pragma: no cover - authenticated org must exist
        raise AppError(404, ErrorCode.NOT_FOUND, "Organization not found")
    return org


async def list_endpoints(
    db: AsyncSession,
    *,
    context: AuthContext,
) -> list[WebhookEndpointRead]:
    org = await _org(db, context.org_id)
    rows = (
        await db.execute(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.org_id == context.org_id)
            .order_by(WebhookEndpoint.created_at, WebhookEndpoint.id)
        )
    ).scalars()
    has_secret = org.webhook_secret_encrypted is not None
    return [endpoint_read(row, has_secret=has_secret) for row in rows]


async def create_endpoint(
    db: AsyncSession,
    *,
    context: AuthContext,
    body: WebhookEndpointCreate,
    settings: Settings,
    policy: SSRFPolicy,
) -> tuple[WebhookEndpointRead, str | None]:
    org = await _org(db, context.org_id, for_update=True)
    existing = (
        await db.execute(
            select(func.count())
            .select_from(WebhookEndpoint)
            .where(WebhookEndpoint.org_id == context.org_id)
        )
    ).scalar_one()
    if existing >= MAX_ENDPOINTS_PER_ORG:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"at most {MAX_ENDPOINTS_PER_ORG} webhook endpoints are allowed",
        )
    url = await _validate_webhook_url(body.url, policy)
    secret: str | None = None
    if org.webhook_secret_encrypted is None:
        secret = generate_secret()
        org.webhook_secret_encrypted = seal_secret(secret, settings)
        org.webhook_secret_created_at = datetime.now(UTC)
    endpoint = WebhookEndpoint(
        org_id=context.org_id,
        created_by=context.user_id,
        url=url,
        description=body.description,
        events=sorted(set(body.events)),
        enabled=body.enabled,
    )
    db.add(endpoint)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            409,
            ErrorCode.CONFLICT,
            "A webhook endpoint with this URL already exists",
        ) from exc
    add_audit(
        db,
        action="webhook.endpoint_created",
        resource_type="webhook_endpoint",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(endpoint.id),
        details={"url": url, "events": endpoint.events},
    )
    await db.commit()
    await db.refresh(endpoint)
    return (
        endpoint_read(endpoint, has_secret=org.webhook_secret_encrypted is not None),
        secret,
    )


async def _get_endpoint(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    endpoint_id: uuid.UUID,
) -> WebhookEndpoint:
    endpoint = (
        await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == endpoint_id,
                WebhookEndpoint.org_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if endpoint is None:
        raise AppError(404, ErrorCode.NOT_FOUND, "Webhook endpoint not found")
    return endpoint


async def update_endpoint(
    db: AsyncSession,
    *,
    context: AuthContext,
    endpoint_id: uuid.UUID,
    body: WebhookEndpointUpdate,
    policy: SSRFPolicy,
) -> WebhookEndpointRead:
    org = await _org(db, context.org_id)
    endpoint = await _get_endpoint(db, org_id=context.org_id, endpoint_id=endpoint_id)
    if body.url is not None:
        endpoint.url = await _validate_webhook_url(body.url, policy)
    if body.description is not None:
        endpoint.description = body.description
    if body.events is not None:
        endpoint.events = sorted(set(body.events))
    if body.enabled is not None:
        endpoint.enabled = body.enabled
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            409,
            ErrorCode.CONFLICT,
            "A webhook endpoint with this URL already exists",
        ) from exc
    add_audit(
        db,
        action="webhook.endpoint_updated",
        resource_type="webhook_endpoint",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(endpoint.id),
    )
    await db.commit()
    await db.refresh(endpoint)
    return endpoint_read(endpoint, has_secret=org.webhook_secret_encrypted is not None)


async def delete_endpoint(
    db: AsyncSession,
    *,
    context: AuthContext,
    endpoint_id: uuid.UUID,
) -> None:
    endpoint = await _get_endpoint(db, org_id=context.org_id, endpoint_id=endpoint_id)
    await db.delete(endpoint)
    add_audit(
        db,
        action="webhook.endpoint_deleted",
        resource_type="webhook_endpoint",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(endpoint_id),
    )
    await db.commit()


async def rotate_secret(
    db: AsyncSession,
    *,
    context: AuthContext,
    settings: Settings,
) -> str:
    org = await _org(db, context.org_id, for_update=True)
    secret = generate_secret()
    org.webhook_secret_encrypted = seal_secret(secret, settings)
    org.webhook_secret_created_at = datetime.now(UTC)
    add_audit(
        db,
        action="webhook.secret_rotated",
        resource_type="organization",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(context.org_id),
    )
    await db.commit()
    return secret


async def list_deliveries(
    db: AsyncSession,
    *,
    context: AuthContext,
    endpoint_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[WebhookDeliveryRead], int]:
    conditions = [WebhookDelivery.org_id == context.org_id]
    if endpoint_id is not None:
        conditions.append(WebhookDelivery.endpoint_id == endpoint_id)
    total = (
        await db.execute(select(func.count()).select_from(WebhookDelivery).where(*conditions))
    ).scalar_one()
    rows = (
        await db.execute(
            select(WebhookDelivery)
            .where(*conditions)
            .order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return [delivery_read(row) for row in rows], int(total)
