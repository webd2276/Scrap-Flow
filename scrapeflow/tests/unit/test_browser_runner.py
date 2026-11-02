from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from apps.api.schemas.automation import AutomationRequest, ClickStep
from apps.worker.browser import runner
from apps.worker.browser.driver import BrowserOptions, build_chrome_options
from packages.core.errors import AppError, ErrorCode
from packages.core.settings import Settings


class FakeDriver:
    session_id = "fake-session"
    current_url = "https://example.com/"
    page_source = "<html><title>Fake</title><body>ok</body></html>"
    quit_called = False

    def __init__(self) -> None:
        self.loaded: list[str] = []
        self.page_timeout: float | None = None
        self.script_timeout: float | None = None

    def get(self, url: str) -> None:
        self.loaded.append(url)
        self.current_url = url

    def set_page_load_timeout(self, value: float) -> None:
        self.page_timeout = value

    def set_script_timeout(self, value: float) -> None:
        self.script_timeout = value

    def get_screenshot_as_png(self) -> bytes:
        return b"\x89PNG-fake"

    def quit(self) -> None:
        self.quit_called = True


def _settings(tmp_path: Path) -> Settings:
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


def test_browser_runner_with_fake_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeDriver()
    monkeypatch.setattr(runner, "register_session", lambda *a, **k: None)
    monkeypatch.setattr(runner, "clear_session", lambda *a, **k: None)

    result = runner.run_browser_page(
        settings=_settings(tmp_path),
        job_id=uuid.uuid4(),
        url="https://example.com/page",
        wait_for=None,
        timeout_seconds=5,
        proxy_url="http://127.0.0.1:9999",
        take_screenshot=True,
        driver_factory=lambda options, settings: fake,
    )
    assert result.final_url == "https://example.com/page"
    assert "Fake" in result.html
    assert result.screenshot_png == b"\x89PNG-fake"
    assert fake.loaded == ["https://example.com/page"]
    assert fake.quit_called is True


class FakeAutomationActions:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.current = "https://example.com/"

    def click(self, selector: str, *, by: str, timeout: float) -> None:
        if self.fail:
            raise AppError(
                422,
                ErrorCode.SELECTOR_NOT_FOUND,
                "Element not found",
                details={"retryable": False},
            )

    def current_url(self) -> str:
        return self.current

    def page_source(self) -> str:
        return "<html><title>Automation</title></html>"

    def screenshot(self, *, full_page: bool) -> bytes:
        return b"\x89PNG-automation"


class FakeAutomationDriver:
    session_id = "fake-session"

    def quit(self) -> None:
        pass


def test_browser_options_clamp_and_flags() -> None:
    options = BrowserOptions(
        proxy_url="http://egress-proxy:8080",
        headless=True,
        no_sandbox=True,
        page_load_timeout=30,
    )
    chrome = build_chrome_options(options)
    arguments = chrome.arguments
    assert "--headless=new" in arguments
    assert "--no-sandbox" in arguments
    assert "--proxy-server=http://egress-proxy:8080" in arguments
    assert any("MAP * ~NOTFOUND" in argument for argument in arguments)
    assert any("EXCLUDE egress-proxy" in argument for argument in arguments)
    assert chrome.capabilities["pageLoadStrategy"] == "normal"


def test_run_automation_success_captures_final_screenshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "register_session", lambda *a, **k: None)
    monkeypatch.setattr(runner, "clear_session", lambda *a, **k: None)
    fake = FakeAutomationActions()
    monkeypatch.setattr(runner, "SeleniumActions", lambda driver: fake)

    request = AutomationRequest(
        url="https://example.com/",
        steps=[{"action": "screenshot", "name": "step"}],
        screenshot=True,
    )
    result = runner.run_automation(
        settings=_settings(tmp_path),
        job_id=uuid.uuid4(),
        request=request,
        secrets={},
        timeout_seconds=5,
        proxy_url="http://127.0.0.1:9999",
        driver_factory=lambda options, settings: FakeAutomationDriver(),
    )

    assert result.failure is None
    assert result.final_url == "https://example.com/"
    assert [shot.name for shot in result.screenshots] == ["step", "final"]
    assert result.step_run.records[0].status == "ok"


def test_run_automation_failure_returns_partial_result_and_screenshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "register_session", lambda *a, **k: None)
    monkeypatch.setattr(runner, "clear_session", lambda *a, **k: None)
    fake = FakeAutomationActions(fail=True)
    monkeypatch.setattr(runner, "SeleniumActions", lambda driver: fake)

    request = AutomationRequest(
        url="https://example.com/",
        steps=[ClickStep(selector="#missing")],
    )
    result = runner.run_automation(
        settings=_settings(tmp_path),
        job_id=uuid.uuid4(),
        request=request,
        secrets={},
        timeout_seconds=5,
        proxy_url="http://127.0.0.1:9999",
        driver_factory=lambda options, settings: FakeAutomationDriver(),
    )

    assert result.failure is not None
    assert result.failure.code == ErrorCode.SELECTOR_NOT_FOUND
    assert result.step_run.records[-1].status == "failed"
    assert [shot.name for shot in result.screenshots] == ["failure"]
