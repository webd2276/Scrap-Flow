"""Schedule request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from packages.core.models import JobKind, ScheduleRunStatus
from packages.core.schedules import (
    normalize_watched_fields,
    validate_cron,
    validate_timezone,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.api.schemas.automation import AutomationRequest
from apps.api.schemas.scrape import JobRead, ScrapeRequest


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    kind: JobKind
    cron: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    enabled: bool = True
    template: dict[str, Any]
    watched_fields: list[str] = Field(default_factory=list, max_length=50)
    notify_on_change: bool = True

    @model_validator(mode="after")
    def _validate_schedule(self) -> ScheduleCreate:
        self.cron = validate_cron(self.cron)
        self.timezone = validate_timezone(self.timezone)
        self.watched_fields = normalize_watched_fields(self.watched_fields)
        validate_schedule_template(self.kind, self.template)
        return self


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    cron: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = None
    template: dict[str, Any] | None = None
    watched_fields: list[str] | None = Field(default=None, max_length=50)
    notify_on_change: bool | None = None

    @model_validator(mode="after")
    def _validate_present_values(self) -> ScheduleUpdate:
        if self.cron is not None:
            self.cron = validate_cron(self.cron)
        if self.timezone is not None:
            self.timezone = validate_timezone(self.timezone)
        if self.watched_fields is not None:
            self.watched_fields = normalize_watched_fields(self.watched_fields)
        return self


class ScheduleRead(BaseModel):
    id: uuid.UUID
    name: str
    kind: JobKind
    cron: str
    timezone: str
    enabled: bool
    template: dict[str, Any]
    watched_fields: list[str]
    notify_on_change: bool
    next_run_at: datetime
    last_run_at: datetime | None
    last_job_id: uuid.UUID | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class ScheduleList(BaseModel):
    items: list[ScheduleRead]
    total: int
    limit: int
    offset: int


class ScheduleRunRead(BaseModel):
    id: uuid.UUID
    schedule_id: uuid.UUID
    job_id: uuid.UUID | None
    trigger: str
    status: ScheduleRunStatus
    scheduled_for: datetime
    credits: int
    error: str | None
    values: dict[str, Any] | None
    changes: list[dict[str, Any]] | None
    created_at: datetime
    finished_at: datetime | None


class ScheduleRunList(BaseModel):
    items: list[ScheduleRunRead]
    total: int
    limit: int
    offset: int


class ScheduleRunNowResponse(BaseModel):
    run: ScheduleRunRead
    job: JobRead


def parse_schedule_template(
    kind: JobKind, template: dict[str, Any]
) -> ScrapeRequest | AutomationRequest:
    """Validate a schedule template with exactly the job schema used at submission."""
    if kind is JobKind.AUTOMATION:
        parsed = AutomationRequest.model_validate(template)
        if parsed.secrets:
            raise ValueError("scheduled automation templates may not contain secrets")
        if parsed.webhook_url:
            raise ValueError("use webhook endpoints instead of webhook_url in schedules")
        return parsed
    scrape = ScrapeRequest.model_validate(template)
    if scrape.webhook_url:
        raise ValueError("use webhook endpoints instead of webhook_url in schedules")
    return scrape


def validate_schedule_template(kind: JobKind, template: dict[str, Any]) -> None:
    try:
        parse_schedule_template(kind, template)
    except ValueError as exc:
        raise ValueError(f"invalid schedule template: {exc}") from exc
