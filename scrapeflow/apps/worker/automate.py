"""Automation execution shared by the Celery task."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from packages.core.artifacts import ArtifactStore
from packages.core.errors import AppError, ErrorCode
from packages.core.models import Job
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy, validate_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.schemas.automation import AutomationRequest
from apps.worker.browser.runner import AutomationRun, run_automation
from apps.worker.browser.steps import StepScreenshot
from apps.worker.extract import extract_page
from apps.worker.http_fetch import JobCancelledError
from apps.worker.scrape import CancelWatcher, ProducedArtifact, egress_proxy
from apps.worker.secrets import delete_secrets, load_secrets


@dataclass(frozen=True, slots=True)
class AutomationOutcome:
    result: dict[str, Any]
    artifacts: tuple[ProducedArtifact, ...]
    failure: AppError | None = None


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AppError(504, ErrorCode.TIMEOUT, "Job exceeded its deadline")
    return remaining


def _build_artifacts(
    *,
    settings: Settings,
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    result: dict[str, Any],
    html: str | None,
    screenshots: list[StepScreenshot],
) -> tuple[ProducedArtifact, ...]:
    store = ArtifactStore(settings)
    produced: list[ProducedArtifact] = []
    result_bytes = json.dumps(result, separators=(",", ":"), sort_keys=True).encode("utf-8")
    produced.append(
        ProducedArtifact(
            kind="result",
            filename="result.json",
            content_type="application/json",
            data=result_bytes,
            stored=store.put(
                org_id=org_id,
                job_id=job_id,
                filename="result.json",
                content_type="application/json",
                data=result_bytes,
            ),
        )
    )
    if html is not None:
        html_bytes = html.encode("utf-8", "replace")
        produced.append(
            ProducedArtifact(
                kind="html",
                filename="page.html",
                content_type="text/html; charset=utf-8",
                data=html_bytes,
                stored=store.put(
                    org_id=org_id,
                    job_id=job_id,
                    filename="page.html",
                    content_type="text/html; charset=utf-8",
                    data=html_bytes,
                ),
            )
        )
    for shot in screenshots:
        filename = f"{shot.name}.png"
        produced.append(
            ProducedArtifact(
                kind="failure_screenshot" if shot.name == "failure" else "screenshot",
                filename=filename,
                content_type="image/png",
                data=shot.data,
                stored=store.put(
                    org_id=org_id,
                    job_id=job_id,
                    filename=filename,
                    content_type="image/png",
                    data=shot.data,
                ),
            )
        )
    return tuple(produced)


def _failure_result(run: AutomationRun, started: float) -> dict[str, Any]:
    payload = {
        "failed": True,
        "error_code": run.failure.code.value if run.failure else None,
        "message": run.failure.message if run.failure else None,
        "failed_step": (run.failure.details if run.failure else None),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
    return {**run.step_run.as_dict(), **payload}


async def execute_automation(
    *,
    job: Job,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    deadline: float,
    policy: SSRFPolicy | None = None,
) -> AutomationOutcome:
    request = AutomationRequest.model_validate(job.payload)
    policy = policy or SSRFPolicy(allowed_ports=settings.egress_port_set)
    started = time.monotonic()

    if settings.selenium_remote_url and not settings.egress_proxy_url:
        raise AppError(
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "Browser jobs require EGRESS_PROXY_URL so Grid traffic is validated",
        )

    cancel = CancelWatcher(sessionmaker, job.id)
    if await cancel():
        raise JobCancelledError

    secrets = await asyncio.to_thread(load_secrets, settings, job.id)
    run: AutomationRun
    try:
        async with egress_proxy(settings, policy) as proxy_url:
            remaining = _remaining(deadline)
            try:
                run = await asyncio.wait_for(
                    asyncio.to_thread(
                        partial(
                            run_automation,
                            settings=settings,
                            job_id=job.id,
                            request=request,
                            secrets=secrets,
                            timeout_seconds=remaining,
                            proxy_url=proxy_url,
                        )
                    ),
                    timeout=remaining + 5,
                )
            except TimeoutError as exc:
                raise AppError(
                    504, ErrorCode.TIMEOUT, "Automation job exceeded its deadline"
                ) from exc

        final = await validate_url(run.final_url or job.url, policy)
        page = extract_page(
            run.html,
            base_url=final.url,
            options=request.extract,
            selectors=request.selectors,
        )
        result: dict[str, Any] = dict(page)
        result.update(
            {
                "url": final.url,
                "render_js": True,
                "redirects": [final.url] if final.url != request.url else [],
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "steps": run.step_run.as_dict()["steps"],
                "extracted": run.step_run.extracted,
            }
        )
        if run.failure is not None:
            result.update(_failure_result(run, started))
            result["steps"] = run.step_run.as_dict()["steps"]

        artifacts = await asyncio.to_thread(
            _build_artifacts,
            settings=settings,
            org_id=job.org_id,
            job_id=job.id,
            result=result,
            html=run.html if request.include_html else None,
            screenshots=run.screenshots,
        )
        return AutomationOutcome(result=result, artifacts=artifacts, failure=run.failure)
    finally:
        # TTL-bounded; never mask the execution result.
        with contextlib.suppress(Exception):
            await asyncio.to_thread(delete_secrets, settings, job.id)


def artifact_expiry(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.artifacts_retention_days)
