from __future__ import annotations

import http.server
import os
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from apps.api.schemas.automation import AutomationRequest
from apps.worker.browser import runner
from packages.core.settings import Settings
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

pytestmark = pytest.mark.browser

CHROME_BINARY = os.getenv("CHROME_BINARY")
CHROMEDRIVER_BINARY = os.getenv("CHROMEDRIVER_BINARY")

PAGE = b"""<!doctype html>
<html><head><title>Local Automation</title></head><body>
<input id="email">
<button id="submit"
  onclick="document.getElementById('message').textContent =
    'hello ' + document.getElementById('email').value">Go</button>
<div id="message"></div>
<select id="color"><option value="red">Red</option><option value="blue">Blue</option></select>
</body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_args: object) -> None:
        pass


@pytest.fixture(scope="module")
def origin() -> Iterator[str]:
    if not CHROME_BINARY or not Path(CHROME_BINARY).exists():
        pytest.skip("CHROME_BINARY is not set; real browser test unavailable")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.shutdown()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        api_key_pepper="a" * 40,
        jwt_secret="b" * 40,
        webhook_secret_key="c" * 40,
        browser_headless=True,
        browser_no_sandbox=True,
        artifacts_local_dir=str(tmp_path),
    )


def _factory(_options: object, _settings: object) -> webdriver.Chrome:
    chrome = Options()
    assert CHROME_BINARY is not None
    chrome.binary_location = CHROME_BINARY
    chrome.add_argument("--headless=new")
    chrome.add_argument("--no-sandbox")
    chrome.add_argument("--disable-dev-shm-usage")
    chrome.add_argument("--disable-gpu")
    service = Service(executable_path=CHROMEDRIVER_BINARY) if CHROMEDRIVER_BINARY else Service()
    driver = webdriver.Chrome(options=chrome, service=service)
    driver.set_page_load_timeout(30)
    return driver


def test_real_browser_runs_steps_and_captures_failure(
    origin: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "register_session", lambda *a, **k: None)
    monkeypatch.setattr(runner, "clear_session", lambda *a, **k: None)
    settings = _settings(tmp_path)

    request = AutomationRequest(
        url=origin,
        steps=[
            {"action": "goto", "url": origin},
            {"action": "type", "selector": "#email", "text": "{{email}}"},
            {"action": "select", "selector": "#color", "value": "blue"},
            {"action": "click", "selector": "#submit"},
            {"action": "wait_for", "selector": "#message"},
            {"action": "get_text", "name": "message", "selector": "#message"},
            {"action": "screenshot", "name": "after-submit"},
        ],
        secrets={"email": "user@example.com"},
        screenshot=True,
    )
    result = runner.run_automation(
        settings=settings,
        job_id=uuid.uuid4(),
        request=request,
        secrets={"email": "user@example.com"},
        timeout_seconds=60,
        proxy_url="http://127.0.0.1:1",
        driver_factory=_factory,
    )
    assert result.failure is None
    assert result.step_run.extracted["message"] == "hello user@example.com"
    assert [record.status for record in result.step_run.records] == ["ok"] * 7
    assert [shot.name for shot in result.screenshots] == ["after-submit", "final"]
    assert all(shot.data.startswith(b"\x89PNG") for shot in result.screenshots)

    failing = AutomationRequest(
        url=origin,
        steps=[
            {"action": "goto", "url": origin},
            {"action": "click", "selector": "#does-not-exist"},
        ],
    )
    failed = runner.run_automation(
        settings=settings,
        job_id=uuid.uuid4(),
        request=failing,
        secrets={},
        timeout_seconds=30,
        proxy_url="http://127.0.0.1:1",
        driver_factory=_factory,
    )
    assert failed.failure is not None
    assert failed.failure.code.value == "SELECTOR_NOT_FOUND"
    assert [shot.name for shot in failed.screenshots] == ["failure"]
    assert failed.screenshots[0].data.startswith(b"\x89PNG")
