"""Stable, typed API errors and the public error envelope."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    BAD_REQUEST = "BAD_REQUEST"
    INVALID_URL = "INVALID_URL"
    BLOCKED_URL = "BLOCKED_URL"
    DNS_FAILURE = "DNS_FAILURE"
    TIMEOUT = "TIMEOUT"
    SELECTOR_NOT_FOUND = "SELECTOR_NOT_FOUND"
    STEP_FAILED = "STEP_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    CONCURRENCY_LIMIT = "CONCURRENCY_LIMIT"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    PAYMENT_REQUIRED = "PAYMENT_REQUIRED"
    BILLING_DISABLED = "BILLING_DISABLED"
    BILLING_ERROR = "BILLING_ERROR"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """An expected failure that is safe to render to the caller."""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | list[Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}

    def envelope(self, request_id: str) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
            },
            "request_id": request_id,
        }


STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    402: ErrorCode.PAYMENT_REQUIRED,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}
