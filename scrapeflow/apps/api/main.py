"""FastAPI application factory.

Settings are injected so tests can construct the app without ambient secrets.
The importable ASGI target lives in ``apps.api.asgi``.
"""

from __future__ import annotations

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from packages.core.checks import ReadinessProbe, build_default_probes
from packages.core.logging import configure_logging
from packages.core.settings import Settings, get_settings

from apps.api.errors import register_error_handlers
from apps.api.middleware.request_context import RequestContextMiddleware
from apps.api.routers import health


def create_app(
    settings: Settings | None = None,
    probes: list[ReadinessProbe] | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved)

    if resolved.sentry_dsn:
        sentry_sdk.init(
            dsn=resolved.sentry_dsn,
            environment=resolved.app_env,
            release=f"scrapeflow@{resolved.app_version}",
            traces_sample_rate=0.05 if resolved.is_production else 0.0,
            send_default_pii=False,
        )

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        docs_url="/docs" if not resolved.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.state.settings = resolved
    app.state.probes = probes if probes is not None else build_default_probes(resolved)

    app.add_middleware(
        RequestContextMiddleware,
        header_name=resolved.request_id_header,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origin_list),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-API-Key",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID", "Retry-After", "X-RateLimit-Remaining"],
    )

    register_error_handlers(app)
    app.include_router(health.router)
    return app
