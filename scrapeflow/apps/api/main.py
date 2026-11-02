"""FastAPI application factory.

Settings are injected so tests can construct the app without ambient secrets.
The importable ASGI target lives in ``apps.api.asgi``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from packages.core.artifacts import ArtifactStore
from packages.core.checks import ReadinessProbe, build_default_probes
from packages.core.db import create_engine, create_sessionmaker
from packages.core.logging import configure_logging
from packages.core.redis import create_redis
from packages.core.settings import Settings, get_settings
from packages.core.ssrf import SSRFPolicy

from apps.api.errors import register_error_handlers
from apps.api.middleware.request_context import RequestContextMiddleware
from apps.api.routers import (
    auth,
    automate,
    billing,
    exports,
    health,
    jobs,
    keys,
    schedules,
    scrape,
    webhooks,
)
from apps.api.services.dispatch import (
    CeleryJobDispatcher,
    JobDispatcher,
    NullDispatcher,
)


def create_app(
    settings: Settings | None = None,
    probes: list[ReadinessProbe] | None = None,
    *,
    dispatcher: JobDispatcher | None = None,
    artifact_store: ArtifactStore | None = None,
    ssrf_policy: SSRFPolicy | None = None,
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

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(resolved)
        application.state.engine = engine
        application.state.sessionmaker = create_sessionmaker(engine)
        application.state.redis = create_redis(resolved)
        try:
            yield
        finally:
            await application.state.redis.aclose()
            await engine.dispose()

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        docs_url="/docs" if not resolved.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.probes = probes if probes is not None else build_default_probes(resolved)
    app.state.dispatcher = dispatcher or (
        CeleryJobDispatcher(resolved) if resolved.queue_enabled else NullDispatcher()
    )
    app.state.artifact_store = artifact_store or ArtifactStore(resolved)
    app.state.ssrf_policy = ssrf_policy or SSRFPolicy(allowed_ports=resolved.egress_port_set)

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
        expose_headers=[
            "X-Request-ID",
            "Retry-After",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Quota-Limit",
            "X-Quota-Remaining",
            "X-Quota-Reset",
            "X-Concurrency-Limit",
            "X-Concurrency-Remaining",
        ],
    )

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(keys.router)
    app.include_router(scrape.router)
    app.include_router(automate.router)
    app.include_router(jobs.router)
    app.include_router(billing.router)
    app.include_router(schedules.router)
    app.include_router(webhooks.router)
    app.include_router(exports.router)
    return app
