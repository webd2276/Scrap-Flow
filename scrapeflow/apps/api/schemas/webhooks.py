"""Webhook endpoint, delivery, and signing-secret schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from packages.core.models import WebhookDeliveryStatus
from pydantic import BaseModel, ConfigDict, Field

WebhookEvent = Literal["job.completed", "job.failed", "job.cancelled", "schedule.changed"]
SUPPORTED_EVENTS: tuple[str, ...] = (
    "job.completed",
    "job.failed",
    "job.cancelled",
    "schedule.changed",
)


def _default_events() -> list[WebhookEvent]:
    return ["job.completed", "job.failed", "job.cancelled"]


class WebhookEndpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    description: str = Field(default="", max_length=200)
    events: list[WebhookEvent] = Field(
        default_factory=_default_events, max_length=len(SUPPORTED_EVENTS)
    )
    enabled: bool = True


class WebhookEndpointUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, min_length=1, max_length=2048)
    description: str | None = Field(default=None, max_length=200)
    events: list[WebhookEvent] | None = Field(default=None, max_length=len(SUPPORTED_EVENTS))
    enabled: bool | None = None


class WebhookEndpointRead(BaseModel):
    id: uuid.UUID
    url: str
    description: str
    events: list[str]
    enabled: bool
    has_secret: bool
    last_success_at: datetime | None
    last_failure_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WebhookEndpointCreated(BaseModel):
    endpoint: WebhookEndpointRead
    secret: str | None = None


class WebhookSecretRead(BaseModel):
    secret: str
    created_at: datetime


class WebhookEndpointList(BaseModel):
    items: list[WebhookEndpointRead]
    total: int


class WebhookDeliveryRead(BaseModel):
    id: uuid.UUID
    endpoint_id: uuid.UUID | None
    url: str
    event_type: str
    status: WebhookDeliveryStatus
    attempts: int
    max_attempts: int
    next_attempt_at: datetime
    response_status: int | None
    response_body: str | None
    error: str | None
    payload: dict[str, Any]
    created_at: datetime
    delivered_at: datetime | None


class WebhookDeliveryList(BaseModel):
    items: list[WebhookDeliveryRead]
    total: int
    limit: int
    offset: int
