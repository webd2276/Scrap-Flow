"""Install the single public error envelope on the API."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from packages.core.errors import STATUS_TO_CODE, AppError, ErrorCode
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.middleware.request_context import current_request_id

logger = structlog.get_logger(__name__)


def error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    *,
    details: dict[str, Any] | list[Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = {
        "error": {"code": code.value, "message": message, "details": details},
        "request_id": current_request_id(),
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.envelope(current_request_id()),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "loc": list(error.get("loc", [])),
                "msg": error.get("msg", "invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return error_response(
            422, ErrorCode.VALIDATION_ERROR, "Request validation failed", details=details
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_TO_CODE.get(exc.status_code, ErrorCode.BAD_REQUEST)
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return error_response(exc.status_code, code, message, headers=dict(exc.headers or {}))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
        return error_response(500, ErrorCode.INTERNAL_ERROR, "An internal error occurred")
