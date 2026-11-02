"""Scrape request/response models shared by the API and the worker."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from packages.core.models import JobKind, JobStatus
from pydantic import BaseModel, Field, field_validator, model_validator

_SELECTOR_LIMIT = 500
_HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")
_FORBIDDEN_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


class SelectorSpec(BaseModel):
    """Exactly one of CSS or XPath. ``all`` returns a bounded list."""

    css: str | None = Field(default=None, min_length=1, max_length=_SELECTOR_LIMIT)
    xpath: str | None = Field(default=None, min_length=1, max_length=_SELECTOR_LIMIT)
    attr: str | None = Field(default=None, min_length=1, max_length=64)
    all: bool = False
    limit: int = Field(default=1, ge=1, le=200)

    @model_validator(mode="after")
    def _exactly_one_query(self) -> SelectorSpec:
        if bool(self.css) == bool(self.xpath):
            raise ValueError("Provide exactly one of css or xpath")
        if self.limit < 1:
            raise ValueError("limit must be at least 1")
        return self


class ExtractOptions(BaseModel):
    title: bool = True
    text: bool = True
    links: bool = False
    meta: bool = False
    max_text_chars: int = Field(default=50_000, ge=10, le=500_000)
    max_links: int = Field(default=200, ge=1, le=1000)


class PaginationOptions(BaseModel):
    next_selector: SelectorSpec
    max_pages: int = Field(default=2, ge=2, le=500)

    @model_validator(mode="after")
    def _next_selector_is_single(self) -> PaginationOptions:
        if self.next_selector.all:
            raise ValueError("next_selector must select a single element")
        if self.next_selector.attr is None:
            self.next_selector.attr = "href"
        return self


class ScrapeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    render_js: bool = False
    wait_for: str | None = Field(default=None, min_length=1, max_length=_SELECTOR_LIMIT)
    selectors: dict[str, SelectorSpec] = Field(default_factory=dict)
    extract: ExtractOptions = Field(default_factory=ExtractOptions)
    screenshot: bool = False
    include_html: bool = False
    pagination: PaginationOptions | None = None
    proxy_country: str | None = Field(default=None, min_length=2, max_length=2)
    webhook_url: str | None = Field(default=None, max_length=2048)
    timeout_seconds: int | None = Field(default=None, ge=10, le=900)
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("url", "webhook_url")
    @classmethod
    def _strip_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("URL must not be empty")
        if any(char in value for char in "\r\n\x00"):
            raise ValueError("URL contains forbidden characters")
        return value

    @field_validator("proxy_country")
    @classmethod
    def _upper_country(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("selectors")
    @classmethod
    def _bounded_selectors(cls, value: dict[str, SelectorSpec]) -> dict[str, SelectorSpec]:
        if len(value) > 50:
            raise ValueError("At most 50 selectors are allowed")
        for name in value:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", name):
                raise ValueError(f"Invalid selector name: {name!r}")
        return value

    @field_validator("headers")
    @classmethod
    def _safe_headers(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 20:
            raise ValueError("At most 20 request headers are allowed")
        cleaned: dict[str, str] = {}
        for name, header_value in value.items():
            if not _HEADER_NAME.fullmatch(name):
                raise ValueError(f"Invalid header name: {name!r}")
            if name.lower() in _FORBIDDEN_HEADERS:
                raise ValueError(f"Header is not allowed: {name}")
            if len(header_value) > 2048 or any(c in header_value for c in "\r\n\x00"):
                raise ValueError(f"Invalid value for header {name}")
            cleaned[name] = header_value
        return cleaned

    @model_validator(mode="after")
    def _screenshot_requires_browser(self) -> ScrapeRequest:
        if self.screenshot and not self.render_js:
            raise ValueError("screenshot requires render_js=true")
        if self.wait_for and not self.render_js:
            raise ValueError("wait_for requires render_js=true")
        host = urlsplit(self.url).hostname
        if host is None or not host.strip():
            raise ValueError("URL must have a host")
        return self


class JobError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class JobRead(BaseModel):
    id: uuid.UUID
    kind: JobKind
    status: JobStatus
    url: str
    result: dict[str, Any] | None = None
    error: JobError | None = None
    attempts: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None
    duration_ms: int | None


class JobAccepted(BaseModel):
    job: JobRead
    deduplicated: bool = False


class JobList(BaseModel):
    items: list[JobRead]
    total: int
    limit: int
    offset: int


class JobEventRead(BaseModel):
    id: uuid.UUID
    type: str
    message: str | None
    data: dict[str, Any]
    created_at: datetime


class ArtifactRead(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    expires_at: datetime | None
    created_at: datetime
    download_url: str
