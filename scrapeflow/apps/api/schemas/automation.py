"""Typed automation steps shared by the API and the worker.

The union is discriminated by ``action`` so unknown actions, missing fields, and
unexpected fields are rejected before a job is accepted. Secrets are referenced
only through ``{{name}}`` placeholders in the three fields that may interpolate
them; the values themselves never enter the job payload.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.api.schemas.scrape import ExtractOptions, SelectorSpec

MAX_STEPS = 500
MAX_DEPTH = 3
_SELECTOR_LIMIT = 500
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_PLACEHOLDER = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]{0,63})\}\}")
_MAX_SECRET_VALUE = 4096
_MAX_SECRETS = 20
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

By = Literal["css", "xpath"]


class AutomationStepBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optional: bool = False
    timeout_s: float = Field(default=10, ge=0.1, le=60)
    retries: int = Field(default=0, ge=0, le=3)


class GotoStep(AutomationStepBase):
    action: Literal["goto"] = "goto"
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        value = value.strip()
        if any(char in value for char in "\r\n\x00"):
            raise ValueError("URL contains forbidden characters")
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("goto URL must be absolute http(s)")
        return value


class ClickStep(AutomationStepBase):
    action: Literal["click"] = "click"
    selector: str = Field(min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"


class TypeStep(AutomationStepBase):
    action: Literal["type"] = "type"
    selector: str = Field(min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"
    text: str = Field(max_length=8192)
    clear: bool = True


class PressStep(AutomationStepBase):
    action: Literal["press"] = "press"
    key: str = Field(min_length=1, max_length=64)
    selector: str | None = Field(default=None, min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"


class SelectStep(AutomationStepBase):
    action: Literal["select"] = "select"
    selector: str = Field(min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"
    value: str = Field(max_length=2048)


class HoverStep(AutomationStepBase):
    action: Literal["hover"] = "hover"
    selector: str = Field(min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"


class WaitForStep(AutomationStepBase):
    action: Literal["wait_for"] = "wait_for"
    selector: str = Field(min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"
    state: Literal["present", "visible"] = "visible"


class SleepStep(AutomationStepBase):
    action: Literal["sleep"] = "sleep"
    seconds: float = Field(ge=0.1, le=30)


class ScrollStep(AutomationStepBase):
    action: Literal["scroll"] = "scroll"
    selector: str | None = Field(default=None, min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"
    x: int = Field(default=0, ge=-100_000, le=100_000)
    y: int = Field(default=0, ge=-100_000, le=100_000)


class ExtractStep(AutomationStepBase):
    action: Literal["extract"] = "extract"
    name: str
    selector: str = Field(min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"
    attr: str | None = Field(default=None, min_length=1, max_length=64)
    all: bool = False
    limit: int = Field(default=1, ge=1, le=200)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("name must match [A-Za-z_][A-Za-z0-9_]{0,63}")
        return value


class GetTextStep(AutomationStepBase):
    action: Literal["get_text"] = "get_text"
    name: str
    selector: str = Field(min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("name must match [A-Za-z_][A-Za-z0-9_]{0,63}")
        return value


class ScreenshotStep(AutomationStepBase):
    action: Literal["screenshot"] = "screenshot"
    name: str | None = Field(default=None, min_length=1, max_length=40)
    full_page: bool = False

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is not None and not _ARTIFACT_NAME.fullmatch(value):
            raise ValueError("name must match [A-Za-z0-9_-]{1,40}")
        return value


class ExecuteIfPresentStep(AutomationStepBase):
    action: Literal["execute_if_present"] = "execute_if_present"
    selector: str = Field(min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"
    steps: list[AutomationStep] = Field(default_factory=list, max_length=MAX_STEPS)

    @model_validator(mode="after")
    def _requires_children(self) -> ExecuteIfPresentStep:
        if not self.steps:
            raise ValueError("execute_if_present requires at least one nested step")
        return self


class LoopPagesStep(AutomationStepBase):
    action: Literal["loop_pages"] = "loop_pages"
    next_selector: str = Field(min_length=1, max_length=_SELECTOR_LIMIT)
    by: By = "css"
    max_pages: int = Field(default=2, ge=2, le=500)
    steps: list[AutomationStep] = Field(default_factory=list, max_length=MAX_STEPS)

    @model_validator(mode="after")
    def _requires_children(self) -> LoopPagesStep:
        if not self.steps:
            raise ValueError("loop_pages requires at least one nested step")
        return self


type AutomationStep = Annotated[
    GotoStep
    | ClickStep
    | TypeStep
    | PressStep
    | SelectStep
    | HoverStep
    | WaitForStep
    | SleepStep
    | ScrollStep
    | ExtractStep
    | GetTextStep
    | ScreenshotStep
    | ExecuteIfPresentStep
    | LoopPagesStep,
    Field(discriminator="action"),
]


_ContainerStep = ExecuteIfPresentStep | LoopPagesStep
_InterpolatedStep = TypeStep | SelectStep | PressStep


def walk_steps(
    steps: list[AutomationStep],
    *,
    depth: int = 1,
) -> list[tuple[AutomationStep, int]]:
    """Yield each step with its nesting depth (root is depth 1)."""
    walked: list[tuple[AutomationStep, int]] = []
    for step in steps:
        walked.append((step, depth))
        if isinstance(step, (ExecuteIfPresentStep, LoopPagesStep)):
            walked.extend(walk_steps(step.steps, depth=depth + 1))
    return walked


def _interpolated_text(step: AutomationStep) -> str | None:
    if isinstance(step, TypeStep):
        return step.text
    if isinstance(step, SelectStep):
        return step.value
    if isinstance(step, PressStep):
        return step.key
    return None


class AutomationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    steps: list[AutomationStep] = Field(min_length=1, max_length=MAX_STEPS)
    secrets: dict[str, str] = Field(default_factory=dict)
    selectors: dict[str, SelectorSpec] = Field(default_factory=dict)
    extract: ExtractOptions = Field(default_factory=ExtractOptions)
    screenshot: bool = False
    include_html: bool = False
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
            if not _NAME.fullmatch(name):
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

    @field_validator("secrets")
    @classmethod
    def _bounded_secrets(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > _MAX_SECRETS:
            raise ValueError(f"At most {_MAX_SECRETS} secrets are allowed")
        total = 0
        for name, secret in value.items():
            if not _NAME.fullmatch(name):
                raise ValueError(f"Invalid secret name: {name!r}")
            if not isinstance(secret, str) or len(secret) > _MAX_SECRET_VALUE:
                raise ValueError(f"Secret {name!r} is too long")
            if "\x00" in secret:
                raise ValueError(f"Secret {name!r} contains a NUL byte")
            total += len(secret)
        if total > 16_384:
            raise ValueError("Secret values exceed 16 KiB in total")
        return value

    @model_validator(mode="after")
    def _validate_graph(self) -> AutomationRequest:
        host = urlsplit(self.url).hostname
        if host is None or not host.strip():
            raise ValueError("URL must have a host")

        walked = walk_steps(self.steps)
        if len(walked) > MAX_STEPS:
            raise ValueError(f"At most {MAX_STEPS} steps are allowed")
        for step, depth in walked:
            if depth > MAX_DEPTH:
                raise ValueError(f"Steps may be nested at most {MAX_DEPTH} levels")
            if isinstance(step, _ContainerStep) and not step.steps:
                raise ValueError(f"{step.action} requires at least one nested step")

        declared = set(self.secrets)
        for step, _depth in walked:
            text = _interpolated_text(step)
            if text is None:
                continue
            for name in _PLACEHOLDER.findall(text):
                if name not in declared:
                    raise ValueError(f"Step references undeclared secret: {name!r}")
            if text.count("{{") != len(_PLACEHOLDER.findall(text)):
                raise ValueError("Malformed secret placeholder; use {{name}}")
        return self


ExecuteIfPresentStep.model_rebuild()
LoopPagesStep.model_rebuild()
AutomationRequest.model_rebuild()

__all__ = [
    "AutomationRequest",
    "AutomationStep",
    "ClickStep",
    "ExecuteIfPresentStep",
    "ExtractStep",
    "GetTextStep",
    "GotoStep",
    "HoverStep",
    "LoopPagesStep",
    "PressStep",
    "ScreenshotStep",
    "ScrollStep",
    "SelectStep",
    "SleepStep",
    "TypeStep",
    "WaitForStep",
    "walk_steps",
]
