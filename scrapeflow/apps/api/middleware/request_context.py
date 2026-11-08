"""Request correlation and access logging as pure ASGI middleware."""

from __future__ import annotations

import re
import time
import uuid
from contextvars import ContextVar

import structlog
from packages.core.observability import observe_http_request
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_METRICS_PATH = "/metrics"


def current_request_id() -> str:
    return request_id_var.get()


class RequestContextMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        header_name: str = "X-Request-ID",
        *,
        metrics_enabled: bool = True,
    ) -> None:
        self.app = app
        self.header_name = header_name
        self.metrics_enabled = metrics_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(self.header_name, "")
        request_id = incoming if _SAFE_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        method = scope.get("method", "")
        path = scope.get("path", "")
        status_code = 500
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers.append(self.header_name, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            duration_seconds = time.perf_counter() - started
            duration_ms = round(duration_seconds * 1000, 2)
            client = scope.get("client")
            structlog.get_logger("scrapeflow.access").info(
                "request",
                method=method,
                path=path,
                status=status_code,
                duration_ms=duration_ms,
                client_ip=client[0] if client else None,
            )
            if self.metrics_enabled and path != _METRICS_PATH:
                observe_http_request(
                    method=method,
                    route=_route_label(scope),
                    status=status_code,
                    duration_seconds=duration_seconds,
                )
            structlog.contextvars.clear_contextvars()
            request_id_var.reset(token)


def _route_label(scope: Scope) -> str:
    """Use the router template, never the raw path, to bound label cardinality."""
    route = scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return "unmatched"
