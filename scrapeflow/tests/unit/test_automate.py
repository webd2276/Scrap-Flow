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
from apps.worker.proxies import ProxyLease
from packages.core.errors import AppError, ErrorCode
from packages.core.models import Job, JobKind, JobStatus
from packages.core.proxies import ProxyEndpoint
from packages.core.settings import Settings
from pydantic import SecretStr


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


class FakeProxyAllocator:
    instances: list[FakeProxyAllocator] = []

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.leases = [
            ProxyLease(
                ProxyEndpoint(
                    id="static-de-1",
                    provider="static",
                    country="DE",
                    url="http://user:secret@a.proxy:8080",
                )
            ),
            ProxyLease(
                ProxyEndpoint(
                    id="static-de-2",
                    provider="static",
                    country="DE",
                    url="http://user:secret@b.proxy:8080",
                )
            ),
        ]
        self.failed: list[str] = []
        self.succeeded: list[str] = []
        FakeProxyAllocator.instances.append(self)

    async def acquire(self, country: str | None) -> ProxyLease:
        assert country == "DE"
        return self.leases.pop(0)

    async def report_failure(self, lease: ProxyLease) -> None:
        self.failed.append(lease.id)

    async def report_success(self, lease: ProxyLease) -> None:
        self.succeeded.append(lease.id)


def _proxy_settings(tmp_path: Any) -> Settings:
    return _settings(tmp_path).model_copy(
        update={
            "proxy_enabled": True,
            "proxy_static_list": SecretStr("DE|http://a.proxy:8080,DE|http://b.proxy:8080"),
            "proxy_health_check_enabled": False,
        }
    )


def _proxy_failure() -> AppError:
    return AppError(
        502,
        ErrorCode.UPSTREAM_ERROR,
        "Browser navigation failed",
        details={"retryable": True, "proxy_failure": True},
    )


@pytest.mark.asyncio
async def test_automation_retries_with_a_different_proxy(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = AutomationRequest(
        url="https://93.184.216.34/",
        steps=[{"action": "goto", "url": "https://93.184.216.34/"}],
        proxy_country="DE",
    )
    failed = AutomationRun(
        final_url="https://93.184.216.34/",
        html="<html></html>",
        step_run=StepRun(),
        failure=_proxy_failure(),
    )
    succeeded = AutomationRun(
        final_url="https://93.184.216.34/",
        html="<html><title>Ok</title></html>",
        step_run=StepRun(records=[StepRecord("0", "goto", "ok", 1)]),
    )
    calls: list[str] = []

    def fake_run(**kwargs: Any) -> AutomationRun:
        calls.append(kwargs["proxy_url"])
        return failed if len(calls) == 1 else succeeded

    @asynccontextmanager
    async def fake_proxy(*_args: Any, **_kwargs: Any) -> Any:
        yield "http://127.0.0.1:9"

    FakeProxyAllocator.instances.clear()
    monkeypatch.setattr(automate, "ProxyAllocator", FakeProxyAllocator)
    monkeypatch.setattr(automate, "egress_proxy", fake_proxy)
    monkeypatch.setattr(automate, "CancelWatcher", NoCancel)
    monkeypatch.setattr(automate, "load_secrets", lambda settings, job_id: {})
    monkeypatch.setattr(automate, "delete_secrets", lambda settings, job_id: None)
    monkeypatch.setattr(automate, "run_automation", fake_run)

    outcome = await automate.execute_automation(
        job=_job(request),
        settings=_proxy_settings(tmp_path),
        sessionmaker=None,  # type: ignore[arg-type]
        deadline=time.monotonic() + 30,
    )

    assert len(calls) == 2
    assert outcome.failure is None
    assert outcome.result["proxy"] == {
        "id": "static-de-2",
        "provider": "static",
        "country": "DE",
    }
    allocator = FakeProxyAllocator.instances[0]
    assert allocator.failed == ["static-de-1"]
    assert allocator.succeeded == ["static-de-2"]
    assert "secret" not in str(outcome.result)


@pytest.mark.asyncio
async def test_automation_does_not_retry_after_a_mutating_step(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = AutomationRequest(
        url="https://93.184.216.34/",
        steps=[
            {"action": "click", "selector": "#submit"},
            {"action": "goto", "url": "https://93.184.216.34/next"},
        ],
        proxy_country="DE",
    )
    failed = AutomationRun(
        final_url="https://93.184.216.34/",
        html="<html></html>",
        step_run=StepRun(records=[StepRecord("0", "click", "ok", 1)]),
        failure=_proxy_failure(),
    )
    calls: list[str] = []

    def fake_run(**kwargs: Any) -> AutomationRun:
        calls.append(kwargs["proxy_url"])
        return failed

    @asynccontextmanager
    async def fake_proxy(*_args: Any, **_kwargs: Any) -> Any:
        yield "http://127.0.0.1:9"

    FakeProxyAllocator.instances.clear()
    monkeypatch.setattr(automate, "ProxyAllocator", FakeProxyAllocator)
    monkeypatch.setattr(automate, "egress_proxy", fake_proxy)
    monkeypatch.setattr(automate, "CancelWatcher", NoCancel)
    monkeypatch.setattr(automate, "load_secrets", lambda settings, job_id: {})
    monkeypatch.setattr(automate, "delete_secrets", lambda settings, job_id: None)
    monkeypatch.setattr(automate, "run_automation", fake_run)

    outcome = await automate.execute_automation(
        job=_job(request),
        settings=_proxy_settings(tmp_path),
        sessionmaker=None,  # type: ignore[arg-type]
        deadline=time.monotonic() + 30,
    )

    assert len(calls) == 1
    assert outcome.failure is not None
    assert outcome.result["proxy"]["id"] == "static-de-1"
    assert FakeProxyAllocator.instances[0].failed == ["static-de-1"]
