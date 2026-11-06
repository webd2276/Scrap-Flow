"""Browser execution for ``render_js=true`` jobs."""

from __future__ import annotations

import contextlib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from packages.core.errors import AppError, ErrorCode
from packages.core.proxies import looks_like_proxy_failure
from packages.core.settings import Settings
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from apps.api.schemas.automation import AutomationRequest
from apps.worker.browser.driver import (
    BrowserOptions,
    SessionWatchdog,
    clear_session,
    create_driver,
    load_page,
    register_session,
    screenshot,
)
from apps.worker.browser.steps import (
    SeleniumActions,
    StepExecutionError,
    StepRun,
    StepScreenshot,
    execute_steps,
    unique_screenshot_name,
)


@dataclass(frozen=True, slots=True)
class BrowserResult:
    final_url: str
    html: str
    screenshot_png: bytes | None


@dataclass(slots=True)
class AutomationRun:
    """Everything the worker needs, including partial output after a failure."""

    final_url: str
    html: str
    step_run: StepRun
    screenshots: list[StepScreenshot] = field(default_factory=list)
    failure: AppError | None = None


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
                    details={
                        "retryable": True,
                        "proxy_failure": looks_like_proxy_failure(exc),
                    },
                ) from exc
            if watchdog.fired:
                raise AppError(504, ErrorCode.TIMEOUT, "Browser job exceeded its deadline")
            png = screenshot(driver) if take_screenshot else None
        return BrowserResult(final_url=final_url, html=html, screenshot_png=png)
    finally:
        clear_session(settings, job_id=job_id)
        with contextlib.suppress(Exception):
            driver.quit()


def run_automation(
    *,
    settings: Settings,
    job_id: uuid.UUID,
    request: AutomationRequest,
    secrets: dict[str, str],
    timeout_seconds: float,
    proxy_url: str,
    driver_factory: Callable[[BrowserOptions, Settings], WebDriver] = create_driver,
) -> AutomationRun:
    """Run an automation script, capturing a failure screenshot and partial output."""
    options = browser_options(settings, proxy_url=proxy_url, timeout_seconds=timeout_seconds)
    driver = driver_factory(options, settings)
    session_id = driver.session_id
    if session_id is None:
        with contextlib.suppress(Exception):
            driver.quit()
        raise AppError(502, ErrorCode.UPSTREAM_ERROR, "Browser session was not created")

    run = StepRun()
    failure: AppError | None = None
    screenshots: list[StepScreenshot] = []
    try:
        register_session(settings, job_id=job_id, session_id=session_id)
        actions = SeleniumActions(driver)
        with SessionWatchdog(driver, timeout_seconds) as watchdog:
            try:
                execute_steps(
                    actions,
                    request.steps,
                    run=run,
                    secrets=secrets,
                    deadline=time.monotonic() + timeout_seconds,
                )
            except StepExecutionError as exc:
                failure = exc.error
            except TimeoutException:
                failure = AppError(
                    504,
                    ErrorCode.TIMEOUT,
                    "Browser action timed out",
                    details={"retryable": False},
                )
            except WebDriverException as exc:
                failure = AppError(
                    502,
                    ErrorCode.UPSTREAM_ERROR,
                    "Browser action failed",
                    details={
                        "retryable": True,
                        "proxy_failure": looks_like_proxy_failure(exc),
                    },
                )
            except AppError as exc:
                failure = exc

            if watchdog.fired:
                failure = AppError(
                    504,
                    ErrorCode.TIMEOUT,
                    "Browser job exceeded its deadline",
                    details={"retryable": False},
                )

            if failure is not None:
                png = _safe_screenshot(actions)
                if png is not None:
                    screenshots.append(StepScreenshot(name="failure", data=png, full_page=False))
            elif request.screenshot:
                screenshots.append(
                    StepScreenshot(
                        name="final",
                        data=actions.screenshot(full_page=False),
                        full_page=False,
                    )
                )

            html = actions.page_source()
            final_url = actions.current_url() or request.url
    finally:
        clear_session(settings, job_id=job_id)
        with contextlib.suppress(Exception):
            driver.quit()

    names: set[str] = set()
    deduped: list[StepScreenshot] = []
    for shot in [*run.screenshots, *screenshots]:
        deduped.append(
            StepScreenshot(
                name=unique_screenshot_name(shot.name, existing=names),
                data=shot.data,
                full_page=shot.full_page,
            )
        )
    return AutomationRun(
        final_url=final_url,
        html=html,
        step_run=run,
        screenshots=deduped,
        failure=failure,
    )


def _safe_screenshot(actions: SeleniumActions) -> bytes | None:
    try:
        return actions.screenshot(full_page=False)
    except (AppError, WebDriverException):
        return None
