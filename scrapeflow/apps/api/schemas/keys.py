"""API key request/response models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from packages.core.scopes import default_key_scopes, validate_scopes
from pydantic import BaseModel, Field, field_validator


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=default_key_scopes)
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def _valid_scopes(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("At least one scope is required")
        return validate_scopes(values)

    @field_validator("expires_at")
    @classmethod
    def _future_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        if value <= datetime.now(UTC):
            raise ValueError("expires_at must be in the future")
        return value


class KeyCreated(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    key: str = Field(description="Shown once; store it securely")
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None


class KeyRead(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
