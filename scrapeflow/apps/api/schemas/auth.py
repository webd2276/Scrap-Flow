"""Auth and account request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class SignupRequest(BaseModel):
    org_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)
    tos_accepted: bool = Field(description="Must be true; the version is recorded")

    @model_validator(mode="after")
    def _require_tos(self) -> SignupRequest:
        if not self.tos_accepted:
            raise ValueError("Terms of Service and acceptable use must be accepted")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    org_slug: str | None = Field(default=None, max_length=80)


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str = Field(description="Also set as an httpOnly cookie for browsers")
    token_type: str = "bearer"
    expires_in: int
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str


class OrgSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str
    plan: str


class MeResponse(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    display_name: str
    tos_accepted_at: datetime | None
    tos_version: str | None
    orgs: list[OrgSummary]
