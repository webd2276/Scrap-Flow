"""Billing request/response models."""

from __future__ import annotations

from typing import Literal

from packages.core.models import OrgPlan
from pydantic import BaseModel, Field, field_validator, model_validator


class CheckoutRequest(BaseModel):
    plan: OrgPlan
    success_url: str | None = Field(default=None, max_length=2048)
    cancel_url: str | None = Field(default=None, max_length=2048)

    @field_validator("success_url", "cancel_url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must be http(s)")
        return value

    @model_validator(mode="after")
    def _paid_plan(self) -> CheckoutRequest:
        if self.plan is OrgPlan.FREE:
            raise ValueError("The free plan does not require checkout")
        return self


class CheckoutResponse(BaseModel):
    url: str


class PortalRequest(BaseModel):
    return_url: str | None = Field(default=None, max_length=2048)

    @field_validator("return_url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must be http(s)")
        return value


class PlanRead(BaseModel):
    code: OrgPlan
    name: str
    monthly_credits: int
    max_concurrency: int
    max_steps: int
    max_pages: int
    artifact_retention_days: int


class UsageRead(BaseModel):
    plan: OrgPlan
    plan_name: str
    period: str
    monthly_credits: int
    used: int
    remaining: int
    reset_seconds: int
    max_concurrency: int
    max_steps: int
    max_pages: int
    artifact_retention_days: int
    billing_enabled: bool


class WebhookResponse(BaseModel):
    received: Literal[True] = True
    duplicate: bool = False
