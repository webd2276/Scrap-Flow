from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest
from apps.api.schemas.automation import AutomationRequest
from apps.worker import automate
from apps.worker.browser.runner import AutomationRun
from apps.worker.browser.steps import StepRecord, StepRun, StepScreenshot
from packages.core.errors import AppError, ErrorCode
from packages.core.models import Job, JobKind, JobStatus
from packages.core.settings import Settings


class NoCancel:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def __call__(self) -> bool:
        return False


def _settings(tmp_path: Any) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        api_key_pepper="a" * 40,
        jwt_secret="b" * 40,
        webhook_secret_key="c" * 40,
        artifacts_local_dir=str(tmp_path),
    )


def _job(request: AutomationRequest) -> Job:
    return Job(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        kind=JobKind.AUTOMATION,
        status=JobStatus.RUNNING,
        url=request.url,
        payload=request.model_dump(mode="json", exclude={"secrets"}),
    )


def _patch(monkeypatch: pytest.MonkeyPatch, run: AutomationRun) -> None:
    @asynccontextmanager
    async def fake_proxy(*_args: Any, **_kwargs: Any) -> Any:
        yield "http://127.0.0.1:9"

    def fake_run(**_kwargs: Any) -> AutomationRun:
        return run

    monkeypatch.setattr(automate, "egress_proxy", fake_proxy)
    monkeypatch.setattr(automate, "CancelWatcher", NoCancel)
    monkeypatch.setattr(automate, "load_secrets", lambda settings, job_id: {})
    monkeypatch.setattr(automate, "delete_secrets", lambda settings, job_id: None)
    monkeypatch.setattr(automate, "run_automation", fake_run)


@pytest.mark.asyncio
async def test_execute_automation_builds_result_and_artifacts(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = AutomationRequest(
        url="https://93.184.216.34/",
        steps=[{"action": "get_text", "name": "title", "selector": "h1"}],
        screenshot=True,
        include_html=True,
    )
    run = AutomationRun(
        final_url="https://93.184.216.34/",
        html="<html><title>Page</title><body><h1>Hello</h1></body></html>",
        step_run=StepRun(
            records=[StepRecord("0", "get_text", "ok", 1, detail="title")],
            extracted={"title": "Hello"},
        ),
        screenshots=[StepScreenshot("final", b"\x89PNG", False)],
    )
    _patch(monkeypatch, run)
    settings = _settings(tmp_path)

    outcome = await automate.execute_automation(
        job=_job(request),
        settings=settings,
        sessionmaker=None,  # type: ignore[arg-type]
        deadline=time.monotonic() + 30,
    )

    assert outcome.failure is None
    assert outcome.result["title"] == "Page"
    assert outcome.result["extracted"] == {"title": "Hello"}
    assert outcome.result["url"] == "https://93.184.216.34:443/"
    assert outcome.result["steps"][0]["status"] == "ok"
    assert [artifact.kind for artifact in outcome.artifacts] == [
        "result",
        "html",
        "screenshot",
    ]
    assert [artifact.filename for artifact in outcome.artifacts] == [
        "result.json",
        "page.html",
        "final.png",
    ]


@pytest.mark.asyncio
async def test_execute_automation_returns_failure_with_failure_screenshot(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = AutomationRequest(
        url="https://93.184.216.34/",
        steps=[{"action": "click", "selector": "#missing"}],
    )
    failure = AppError(
        422,
        ErrorCode.SELECTOR_NOT_FOUND,
        "Element not found",
        details={"retryable": False, "step": "0", "action": "click"},
    )
    run = AutomationRun(
        final_url="https://93.184.216.34/",
        html="<html></html>",
        step_run=StepRun(records=[StepRecord("0", "click", "failed", 1)]),
        screenshots=[StepScreenshot("failure", b"\x89PNG", False)],
        failure=failure,
    )
    _patch(monkeypatch, run)
    settings = _settings(tmp_path)

    outcome = await automate.execute_automation(
        job=_job(request),
        settings=settings,
        sessionmaker=None,  # type: ignore[arg-type]
        deadline=time.monotonic() + 30,
    )

    assert outcome.failure is failure
    assert outcome.result["failed"] is True
    assert outcome.result["error_code"] == "SELECTOR_NOT_FOUND"
    assert outcome.result["failed_step"]["step"] == "0"
    assert [artifact.kind for artifact in outcome.artifacts] == [
        "result",
        "failure_screenshot",
    ]
