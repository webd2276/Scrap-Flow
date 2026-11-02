"""Browser execution for ``render_js=true`` jobs."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from packages.core.errors import AppError, ErrorCode
from packages.core.settings import Settings
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from apps.worker.browser.driver import (
    BrowserOptions,
    SessionWatchdog,
    clear_session,
    create_driver,
    load_page,
    register_session,
    screenshot,
)


@dataclass(frozen=True, slots=True)
class BrowserResult:
    final_url: str
    html: str
    screenshot_png: bytes | None


def browser_options(
    settings: Settings,
    *,
    proxy_url: str,
    timeout_seconds: float,
) -> BrowserOptions:
    page_timeout = max(
        1,
        min(
            int(timeout_seconds),
            settings.browser_page_load_timeout_seconds,
        ),
    )
    return BrowserOptions(
        proxy_url=proxy_url,
        headless=settings.browser_headless,
        no_sandbox=settings.browser_no_sandbox,
        page_load_timeout=page_timeout,
    )


def run_browser_page(
    *,
    settings: Settings,
    job_id: uuid.UUID,
    url: str,
    wait_for: str | None,
    timeout_seconds: float,
    proxy_url: str,
    take_screenshot: bool,
    driver_factory: Callable[[BrowserOptions, Settings], WebDriver] = create_driver,
) -> BrowserResult:
    options = browser_options(settings, proxy_url=proxy_url, timeout_seconds=timeout_seconds)
    driver = driver_factory(options, settings)
    session_id = driver.session_id
    if session_id is None:
        with contextlib.suppress(Exception):
            driver.quit()
        raise AppError(502, ErrorCode.UPSTREAM_ERROR, "Browser session was not created")
    try:
        register_session(settings, job_id=job_id, session_id=session_id)
        with SessionWatchdog(driver, timeout_seconds) as watchdog:
            try:
                final_url, html = load_page(
                    driver,
                    url=url,
                    wait_for=wait_for,
                    timeout=max(1.0, timeout_seconds),
                )
            except TimeoutException as exc:
                raise AppError(504, ErrorCode.TIMEOUT, "Browser page load timed out") from exc
            except WebDriverException as exc:
                raise AppError(
                    502,
                    ErrorCode.UPSTREAM_ERROR,
                    "Browser navigation failed",
                ) from exc
            if watchdog.fired:
                raise AppError(504, ErrorCode.TIMEOUT, "Browser job exceeded its deadline")
            png = screenshot(driver) if take_screenshot else None
        return BrowserResult(final_url=final_url, html=html, screenshot_png=png)
    finally:
        clear_session(settings, job_id=job_id)
        with contextlib.suppress(Exception):
            driver.quit()
