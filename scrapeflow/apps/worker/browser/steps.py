"""Typed automation step execution.

The executor talks to a small ``BrowserActions`` protocol so step semantics,
retries, optional handling, interpolation, and result shaping can be tested
without Selenium. ``SeleniumActions`` is the production adapter.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from packages.core.errors import AppError, ErrorCode
from packages.core.proxies import looks_like_proxy_failure
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    InvalidSelectorException,
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import Select, WebDriverWait

from apps.api.schemas.automation import (
    AutomationStep,
    ClickStep,
    ExecuteIfPresentStep,
    ExtractStep,
    GetTextStep,
    GotoStep,
    HoverStep,
    LoopPagesStep,
    PressStep,
    ScreenshotStep,
    ScrollStep,
    SelectStep,
    SleepStep,
    TypeStep,
    WaitForStep,
)

_PLACEHOLDER = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]{0,63})\}\}")
_WHITESPACE = re.compile(r"\s+")
_WAIT_SLICE = 0.5

_SPECIAL_KEYS: dict[str, str] = {
    "ENTER": Keys.ENTER,
    "RETURN": Keys.RETURN,
    "TAB": Keys.TAB,
    "ESCAPE": Keys.ESCAPE,
    "ESC": Keys.ESCAPE,
    "SPACE": Keys.SPACE,
    "BACKSPACE": Keys.BACKSPACE,
    "DELETE": Keys.DELETE,
    "ARROWUP": Keys.ARROW_UP,
    "ARROWDOWN": Keys.ARROW_DOWN,
    "ARROWLEFT": Keys.ARROW_LEFT,
    "ARROWRIGHT": Keys.ARROW_RIGHT,
    "PAGEUP": Keys.PAGE_UP,
    "PAGEDOWN": Keys.PAGE_DOWN,
    "HOME": Keys.HOME,
    "END": Keys.END,
}


class BrowserActions(Protocol):
    def goto(self, url: str, *, timeout: float) -> str: ...

    def current_url(self) -> str: ...

    def page_source(self) -> str: ...

    def click(self, selector: str, *, by: str, timeout: float) -> None: ...

    def type_text(
        self, selector: str, text: str, *, by: str, clear: bool, timeout: float
    ) -> None: ...

    def press(self, key: str, *, selector: str | None, by: str, timeout: float) -> None: ...

    def select_option(self, selector: str, value: str, *, by: str, timeout: float) -> None: ...

    def hover(self, selector: str, *, by: str, timeout: float) -> None: ...

    def wait_for(self, selector: str, *, by: str, state: str, timeout: float) -> None: ...

    def sleep(self, seconds: float) -> None: ...

    def scroll(
        self,
        *,
        selector: str | None,
        by: str,
        x: int,
        y: int,
        timeout: float,
    ) -> None: ...

    def exists(self, selector: str, *, by: str, timeout: float) -> bool: ...

    def text(self, selector: str, *, by: str, timeout: float) -> str: ...

    def values(
        self,
        selector: str,
        *,
        by: str,
        attr: str | None,
        timeout: float,
    ) -> list[str]: ...

    def screenshot(self, *, full_page: bool) -> bytes: ...


@dataclass(frozen=True, slots=True)
class StepScreenshot:
    name: str
    data: bytes
    full_page: bool


@dataclass(slots=True)
class StepRecord:
    path: str
    action: str
    status: str
    duration_ms: int
    error_code: str | None = None
    detail: str | None = None
    artifact: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "action": self.action,
            "status": self.status,
            "duration_ms": self.duration_ms,
        }
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        if self.detail is not None:
            payload["detail"] = self.detail
        if self.artifact is not None:
            payload["artifact"] = self.artifact
        return payload


@dataclass(slots=True)
class StepRun:
    """Mutable accumulation of step output, safe to inspect after a failure."""

    records: list[StepRecord] = field(default_factory=list)
    extracted: dict[str, Any] = field(default_factory=dict)
    screenshots: list[StepScreenshot] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "steps": [record.as_dict() for record in self.records],
            "extracted": self.extracted,
        }


class StepExecutionError(Exception):
    def __init__(self, error: AppError, *, path: str, action: str) -> None:
        super().__init__(error.message)
        self.error = error
        self.path = path
        self.action = action


def _normalise(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def resolve_secrets(text: str, secrets: dict[str, str]) -> str:
    """Replace ``{{name}}`` placeholders, failing closed on missing material."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        try:
            return secrets[name]
        except KeyError as exc:
            raise AppError(
                422,
                ErrorCode.STEP_FAILED,
                f"Secret material for {name!r} is unavailable",
                details={"secret": name, "retryable": False},
            ) from exc

    return _PLACEHOLDER.sub(replace, text)


def redact(text: str, secrets: dict[str, str]) -> str:
    """Remove known secret values from a string before it can be recorded."""
    redacted = text
    for value in sorted(secrets.values(), key=len, reverse=True):
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AppError(504, ErrorCode.TIMEOUT, "Job exceeded its deadline")
    return remaining


def _is_retryable(error: AppError) -> bool:
    details = error.details
    return bool(isinstance(details, dict) and details.get("retryable"))


def _record(
    run: StepRun,
    *,
    path: str,
    action: str,
    status: str,
    started: float,
    error_code: str | None = None,
    detail: str | None = None,
    artifact: str | None = None,
) -> None:
    run.records.append(
        StepRecord(
            path=path,
            action=action,
            status=status,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_code=error_code,
            detail=detail,
            artifact=artifact,
        )
    )


def _execute(
    actions: BrowserActions,
    step: AutomationStep,
    *,
    run: StepRun,
    secrets: dict[str, str],
    deadline: float,
    path: str,
    depth: int,
) -> str | None:
    timeout = min(float(step.timeout_s), _remaining(deadline))

    if isinstance(step, GotoStep):
        actions.goto(step.url, timeout=timeout)
        return "navigated"
    if isinstance(step, ClickStep):
        actions.click(step.selector, by=step.by, timeout=timeout)
        return None
    if isinstance(step, TypeStep):
        actions.type_text(
            step.selector,
            resolve_secrets(step.text, secrets),
            by=step.by,
            clear=step.clear,
            timeout=timeout,
        )
        return None
    if isinstance(step, PressStep):
        actions.press(
            resolve_secrets(step.key, secrets),
            selector=step.selector,
            by=step.by,
            timeout=timeout,
        )
        return None
    if isinstance(step, SelectStep):
        actions.select_option(
            step.selector,
            resolve_secrets(step.value, secrets),
            by=step.by,
            timeout=timeout,
        )
        return None
    if isinstance(step, HoverStep):
        actions.hover(step.selector, by=step.by, timeout=timeout)
        return None
    if isinstance(step, WaitForStep):
        actions.wait_for(step.selector, by=step.by, state=step.state, timeout=timeout)
        return None
    if isinstance(step, SleepStep):
        actions.sleep(min(step.seconds, _remaining(deadline)))
        return None
    if isinstance(step, ScrollStep):
        actions.scroll(
            selector=step.selector,
            by=step.by,
            x=step.x,
            y=step.y,
            timeout=timeout,
        )
        return None
    if isinstance(step, ExtractStep):
        values = actions.values(
            step.selector,
            by=step.by,
            attr=step.attr,
            timeout=timeout,
        )
        value: str | list[str] | None
        value = values[: step.limit] if step.all else (values[0] if values else None)
        run.extracted[step.name] = value
        return step.name
    if isinstance(step, GetTextStep):
        run.extracted[step.name] = actions.text(step.selector, by=step.by, timeout=timeout)
        return step.name
    if isinstance(step, ScreenshotStep):
        name = step.name or f"screenshot_{path.replace('.', '_')}"
        run.screenshots.append(
            StepScreenshot(
                name=name,
                data=actions.screenshot(full_page=step.full_page),
                full_page=step.full_page,
            )
        )
        return name
    if isinstance(step, ExecuteIfPresentStep):
        if not actions.exists(step.selector, by=step.by, timeout=min(_WAIT_SLICE, timeout)):
            return "absent"
        execute_steps(
            actions,
            step.steps,
            run=run,
            secrets=secrets,
            deadline=deadline,
            path_prefix=f"{path}.",
            depth=depth + 1,
        )
        return "executed"
    if isinstance(step, LoopPagesStep):
        pages = 0
        for page in range(step.max_pages):
            execute_steps(
                actions,
                step.steps,
                run=run,
                secrets=secrets,
                deadline=deadline,
                path_prefix=f"{path}[{page}].",
                depth=depth + 1,
            )
            pages += 1
            if page == step.max_pages - 1:
                break
            if not actions.exists(
                step.next_selector, by=step.by, timeout=min(_WAIT_SLICE, timeout)
            ):
                break
            before = actions.current_url()
            actions.click(step.next_selector, by=step.by, timeout=timeout)
            if actions.current_url() == before:
                break
        return f"{pages} page(s)"

    raise AppError(500, ErrorCode.INTERNAL_ERROR, f"Unsupported step: {step.action}")


def execute_steps(
    actions: BrowserActions,
    steps: list[AutomationStep],
    *,
    run: StepRun,
    secrets: dict[str, str],
    deadline: float,
    path_prefix: str = "",
    depth: int = 1,
) -> None:
    """Execute steps in order, honouring retries, optional steps, and the deadline."""
    for index, step in enumerate(steps):
        path = f"{path_prefix}{index}"
        started = time.monotonic()
        attempt = 0
        while True:
            try:
                detail = _execute(
                    actions,
                    step,
                    run=run,
                    secrets=secrets,
                    deadline=deadline,
                    path=path,
                    depth=depth,
                )
                _record(
                    run,
                    path=path,
                    action=step.action,
                    status="ok",
                    started=started,
                    detail=detail,
                )
                break
            except AppError as error:
                if _is_retryable(error) and attempt < step.retries and _remaining(deadline) > 0.2:
                    attempt += 1
                    time.sleep(min(0.25 * (2**attempt), 1.5))
                    continue
                if step.optional:
                    _record(
                        run,
                        path=path,
                        action=step.action,
                        status="skipped",
                        started=started,
                        error_code=error.code.value,
                        detail=redact(error.message, secrets),
                    )
                    break
                merged = AppError(
                    error.status_code,
                    error.code,
                    redact(error.message, secrets),
                    details={
                        **(error.details if isinstance(error.details, dict) else {}),
                        "step": path,
                        "action": step.action,
                        "attempts": attempt + 1,
                    },
                )
                _record(
                    run,
                    path=path,
                    action=step.action,
                    status="failed",
                    started=started,
                    error_code=merged.code.value,
                    detail=merged.message,
                )
                raise StepExecutionError(merged, path=path, action=step.action) from error


def _by(by: str) -> str:
    return By.XPATH if by == "xpath" else By.CSS_SELECTOR


def _wrap(error: Exception, *, selector: str | None = None, retryable: bool = False) -> AppError:
    """Translate Selenium failures into stable, value-free AppErrors."""
    if isinstance(error, InvalidSelectorException):
        return AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Invalid selector",
            details={"retryable": False},
        )
    if isinstance(error, NoSuchElementException):
        return AppError(
            422,
            ErrorCode.SELECTOR_NOT_FOUND,
            "Element not found",
            details={"retryable": False, **({"selector": selector} if selector else {})},
        )
    if isinstance(error, TimeoutException):
        return AppError(
            422,
            ErrorCode.SELECTOR_NOT_FOUND,
            "Timed out waiting for the element",
            details={"retryable": retryable, **({"selector": selector} if selector else {})},
        )
    return AppError(
        502,
        ErrorCode.UPSTREAM_ERROR,
        "Browser action failed",
        details={
            "retryable": True,
            "proxy_failure": looks_like_proxy_failure(error),
            **({"selector": selector} if selector else {}),
        },
    )


class SeleniumActions:
    """Production adapter over a Selenium WebDriver."""

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    def _find(
        self,
        selector: str,
        *,
        by: str,
        timeout: float,
        clickable: bool = False,
    ) -> WebElement:
        condition = (
            ec.element_to_be_clickable((_by(by), selector))
            if clickable
            else ec.presence_of_element_located((_by(by), selector))
        )
        try:
            element = WebDriverWait(self.driver, max(0.1, timeout)).until(condition)
        except (TimeoutException, NoSuchElementException, InvalidSelectorException) as exc:
            raise _wrap(exc, selector=selector, retryable=True) from exc
        return element

    def goto(self, url: str, *, timeout: float) -> str:
        try:
            self.driver.get(url)
        except TimeoutException as exc:
            raise AppError(
                504,
                ErrorCode.TIMEOUT,
                "Page load timed out",
                details={"retryable": False},
            ) from exc
        except WebDriverException as exc:
            raise _wrap(exc) from exc
        return str(self.driver.current_url)

    def current_url(self) -> str:
        try:
            return str(self.driver.current_url)
        except WebDriverException:
            return ""

    def page_source(self) -> str:
        try:
            return str(self.driver.page_source)
        except WebDriverException:
            return ""

    def click(self, selector: str, *, by: str, timeout: float) -> None:
        element = self._find(selector, by=by, timeout=timeout, clickable=True)
        try:
            element.click()
        except ElementClickInterceptedException:
            try:
                self.driver.execute_script("arguments[0].click();", element)
            except WebDriverException as exc:
                raise _wrap(exc, selector=selector, retryable=True) from exc
        except (NoSuchElementException, TimeoutException, InvalidSelectorException) as exc:
            raise _wrap(exc, selector=selector) from exc
        except WebDriverException as exc:
            raise _wrap(exc, selector=selector, retryable=True) from exc

    def type_text(
        self,
        selector: str,
        text: str,
        *,
        by: str,
        clear: bool,
        timeout: float,
    ) -> None:
        element = self._find(selector, by=by, timeout=timeout)
        try:
            if clear:
                element.clear()
            element.send_keys(text)
        except (NoSuchElementException, TimeoutException, InvalidSelectorException) as exc:
            raise _wrap(exc, selector=selector) from exc
        except WebDriverException as exc:
            raise _wrap(exc, selector=selector, retryable=True) from exc

    def press(self, key: str, *, selector: str | None, by: str, timeout: float) -> None:
        send = _SPECIAL_KEYS.get(key.upper(), key)
        try:
            target: WebElement | None
            if selector:
                target = self._find(selector, by=by, timeout=timeout)
            else:
                target = self.driver.find_element(By.TAG_NAME, "body")
            target.send_keys(send)
        except (NoSuchElementException, TimeoutException, InvalidSelectorException) as exc:
            raise _wrap(exc, selector=selector) from exc
        except WebDriverException as exc:
            raise _wrap(exc, selector=selector, retryable=True) from exc

    def select_option(self, selector: str, value: str, *, by: str, timeout: float) -> None:
        element = self._find(selector, by=by, timeout=timeout)
        try:
            Select(element).select_by_value(value)
        except (NoSuchElementException, TimeoutException, InvalidSelectorException) as exc:
            raise _wrap(exc, selector=selector) from exc
        except WebDriverException as exc:
            raise _wrap(exc, selector=selector) from exc

    def hover(self, selector: str, *, by: str, timeout: float) -> None:
        element = self._find(selector, by=by, timeout=timeout)
        try:
            ActionChains(self.driver).move_to_element(element).perform()
        except (NoSuchElementException, TimeoutException, InvalidSelectorException) as exc:
            raise _wrap(exc, selector=selector) from exc
        except WebDriverException as exc:
            raise _wrap(exc, selector=selector, retryable=True) from exc

    def wait_for(self, selector: str, *, by: str, state: str, timeout: float) -> None:
        condition = (
            ec.visibility_of_element_located((_by(by), selector))
            if state == "visible"
            else ec.presence_of_element_located((_by(by), selector))
        )
        try:
            WebDriverWait(self.driver, max(0.1, timeout)).until(condition)
        except (TimeoutException, NoSuchElementException, InvalidSelectorException) as exc:
            raise _wrap(exc, selector=selector, retryable=False) from exc

    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))

    def scroll(
        self,
        *,
        selector: str | None,
        by: str,
        x: int,
        y: int,
        timeout: float,
    ) -> None:
        try:
            if selector:
                element = self._find(selector, by=by, timeout=timeout)
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", element
                )
            else:
                self.driver.execute_script(f"window.scrollBy({x}, {y});")
        except (NoSuchElementException, TimeoutException, InvalidSelectorException) as exc:
            raise _wrap(exc, selector=selector) from exc
        except WebDriverException as exc:
            raise _wrap(exc, selector=selector, retryable=True) from exc

    def exists(self, selector: str, *, by: str, timeout: float) -> bool:
        try:
            WebDriverWait(self.driver, max(0.1, timeout)).until(
                lambda driver: bool(driver.find_elements(_by(by), selector))
            )
        except (TimeoutException, NoSuchElementException, InvalidSelectorException):
            return False
        except WebDriverException as exc:
            raise _wrap(exc, selector=selector, retryable=True) from exc
        return True

    def text(self, selector: str, *, by: str, timeout: float) -> str:
        element = self._find(selector, by=by, timeout=timeout)
        try:
            return _normalise(str(element.text))
        except WebDriverException as exc:
            raise _wrap(exc, selector=selector, retryable=True) from exc

    def values(
        self,
        selector: str,
        *,
        by: str,
        attr: str | None,
        timeout: float,
    ) -> list[str]:
        query = _by(by)
        try:
            WebDriverWait(self.driver, max(0.1, timeout)).until(
                lambda driver: bool(driver.find_elements(query, selector))
            )
            elements = self.driver.find_elements(query, selector)
        except (TimeoutException, NoSuchElementException):
            return []
        except InvalidSelectorException as exc:
            raise _wrap(exc, selector=selector) from exc
        except WebDriverException as exc:
            raise _wrap(exc, selector=selector, retryable=True) from exc

        values: list[str] = []
        for element in elements:
            if attr:
                value = element.get_attribute(attr)
                if value is None:
                    continue
                values.append(_normalise(str(value)))
            else:
                value = _normalise(str(element.text))
                if value:
                    values.append(value)
        return values

    def screenshot(self, *, full_page: bool) -> bytes:
        if full_page:
            try:
                result = self.driver.execute_cdp_cmd(
                    "Page.captureScreenshot",
                    {"format": "png", "captureBeyondViewport": True},
                )
                data = result.get("data")
                if isinstance(data, str):
                    return base64.b64decode(data)
            except (WebDriverException, ValueError):
                pass
        try:
            return bytes(self.driver.get_screenshot_as_png())
        except WebDriverException as exc:
            raise _wrap(exc, retryable=True) from exc


def unique_screenshot_name(name: str, *, existing: set[str]) -> str:
    """Keep artifact filenames unique without trusting user input for paths."""
    candidate = name
    if candidate not in existing:
        existing.add(candidate)
        return candidate
    suffix = uuid4().hex[:8]
    candidate = f"{name}_{suffix}"
    existing.add(candidate)
    return candidate
