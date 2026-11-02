"""Webhook endpoint management, secret rotation, and delivery log."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, Response, status
from packages.core.db import get_db
from packages.core.scopes import Scope
from packages.core.settings import Settings
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import AuthContext, get_app_settings, org_rate_limit, require_scope
from apps.api.schemas.webhooks import (
    WebhookDeliveryList,
    WebhookEndpointCreate,
    WebhookEndpointCreated,
    WebhookEndpointList,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
    WebhookSecretRead,
)
from apps.api.services import webhooks as webhook_service

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


@router.get("", response_model=WebhookEndpointList)
async def list_endpoints(
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.SCHEDULES_WRITE)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> WebhookEndpointList:
    items = await webhook_service.list_endpoints(db, context=context)
    return WebhookEndpointList(items=items, total=len(items))


@router.post("", response_model=WebhookEndpointCreated, status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    body: WebhookEndpointCreate,
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.SCHEDULES_WRITE)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    _: None = Depends(org_rate_limit),
) -> WebhookEndpointCreated:
    endpoint, secret = await webhook_service.create_endpoint(
        db,
        context=context,
        body=body,
        settings=settings,
        policy=request.app.state.ssrf_policy,
    )
    return WebhookEndpointCreated(endpoint=endpoint, secret=secret)


@router.patch("/{endpoint_id}", response_model=WebhookEndpointRead)
async def update_endpoint(
    endpoint_id: uuid.UUID,
    body: WebhookEndpointUpdate,
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.SCHEDULES_WRITE)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> WebhookEndpointRead:
    return await webhook_service.update_endpoint(
        db,
        context=context,
        endpoint_id=endpoint_id,
        body=body,
        policy=request.app.state.ssrf_policy,
    )


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    endpoint_id: uuid.UUID,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.SCHEDULES_WRITE)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> Response:
    await webhook_service.delete_endpoint(db, context=context, endpoint_id=endpoint_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/rotate-secret", response_model=WebhookSecretRead)
async def rotate_secret(
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.SCHEDULES_WRITE)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    _: None = Depends(org_rate_limit),
) -> WebhookSecretRead:
    secret = await webhook_service.rotate_secret(db, context=context, settings=settings)
    return WebhookSecretRead(secret=secret, created_at=datetime.now(UTC))


@router.get("/deliveries", response_model=WebhookDeliveryList)
async def list_deliveries(
    response: Response,
    endpoint_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    context: AuthContext = Depends(require_scope(Scope.JOBS_READ)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> WebhookDeliveryList:
    items, total = await webhook_service.list_deliveries(
        db,
        context=context,
        endpoint_id=endpoint_id,
        limit=limit,
        offset=offset,
    )
    return WebhookDeliveryList(items=items, total=total, limit=limit, offset=offset)
