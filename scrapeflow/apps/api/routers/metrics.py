"""Prometheus exposition endpoint and scrape-time runtime sampling."""

from __future__ import annotations

import asyncio
import hmac
import time

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import Response
from packages.core.errors import AppError, ErrorCode
from packages.core.observability import (
    ACTIVE_BROWSER_SESSIONS,
    DB_LATENCY_SECONDS,
    QUEUE_DEPTH,
    REDIS_LATENCY_SECONDS,
    WEBHOOK_PENDING,
    render_metrics,
)
from packages.core.settings import Settings
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter(tags=["system"])
logger = structlog.get_logger(__name__)

SESSION_PREFIX = "sf:browser:session:"
_PENDING_SQL = text(
    "SELECT 1 AS ok, (SELECT count(*) FROM webhook_deliveries WHERE status = 'pending') AS pending"
)


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    if not settings.metrics_enabled:
        raise AppError(404, ErrorCode.NOT_FOUND, "Metrics are disabled")
    _require_token(request, settings)

    try:
        await asyncio.wait_for(
            collect_runtime_metrics(
                request.app.state.redis,
                request.app.state.engine,
                settings,
            ),
            timeout=max(1.0, settings.readiness_timeout_seconds),
        )
    except Exception as exc:
        # A slow database must not take down the scrape endpoint; the last
        # sampled gauges and the request/job counters remain useful.
        logger.warning("metrics.runtime_sample_failed", error=type(exc).__name__)

    payload, content_type = render_metrics()
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


def _require_token(request: Request, settings: Settings) -> None:
    if settings.metrics_token is None:
        return
    expected = settings.metrics_token.get_secret_value()
    header = request.headers.get("authorization", "")
    scheme, _, supplied = header.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        supplied.encode("utf-8"), expected.encode("utf-8")
    ):
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Metrics credentials required")


async def collect_runtime_metrics(
    redis: Redis,
    engine: AsyncEngine,
    settings: Settings,
) -> None:
    """Sample Redis queue depth, registered browser sessions, and latencies."""
    queues = settings.metrics_queue_list
    started = time.perf_counter()
    async with redis.pipeline(transaction=False) as pipe:
        for queue in queues:
            pipe.llen(queue)
        pipe.ping()
        results = await pipe.execute()
    REDIS_LATENCY_SECONDS.set(time.perf_counter() - started)

    for queue, depth in zip(queues, results[: len(queues)], strict=True):
        QUEUE_DEPTH.labels(queue=queue).set(float(depth or 0))

    sessions = 0
    async for _key in redis.scan_iter(match=f"{SESSION_PREFIX}*", count=1000):
        sessions += 1
    ACTIVE_BROWSER_SESSIONS.set(sessions)

    started = time.perf_counter()
    async with engine.connect() as connection:
        row = (await connection.execute(_PENDING_SQL)).one()
    DB_LATENCY_SECONDS.set(time.perf_counter() - started)
    WEBHOOK_PENDING.set(float(row[1] or 0))
