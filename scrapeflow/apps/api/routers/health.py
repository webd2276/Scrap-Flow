"""Liveness and readiness endpoints. Neither requires authentication."""

from __future__ import annotations

from fastapi import APIRouter, Request
from packages.core.checks import ReadinessProbe, run_probes
from packages.core.errors import AppError, ErrorCode
from packages.core.settings import Settings

router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness probe")
async def health(request: Request) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    return {"status": "ok", "version": settings.app_version, "environment": settings.app_env}


@router.get("/ready", summary="Readiness probe")
async def ready(request: Request) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    probes: list[ReadinessProbe] = request.app.state.probes
    results = await run_probes(probes, timeout_s=settings.readiness_timeout_seconds)
    if any(result["status"] != "ok" for result in results.values()):
        raise AppError(
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "Service is not ready",
            details={"checks": results},
        )
    return {"status": "ready", "checks": results}
