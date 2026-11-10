"""Selenium driver construction and session bookkeeping."""

from __future__ import annotations

import contextlib
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import redis
from packages.core.settings import Settings
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

DriverFactory = Callable[["BrowserOptions"], webdriver.Remote]

SESSION_KEY = "sf:browser:session:{job_id}"


@dataclass(frozen=True, slots=True)
class BrowserOptions:
    proxy_url: str
    headless: bool
    no_sandbox: bool
    page_load_timeout: int
    window_width: int = 1366
    window_height: int = 768


def build_chrome_options(options: BrowserOptions) -> Options:
    chrome = Options()
    if options.headless:
        chrome.add_argument("--headless=new")
    if options.no_sandbox:
        chrome.add_argument("--no-sandbox")
    chrome.add_argument("--disable-dev-shm-usage")
    chrome.add_argument("--disable-gpu")
    chrome.add_argument("--disable-background-networking")
    chrome.add_argument("--disable-component-update")
    chrome.add_argument("--disable-default-apps")
    chrome.add_argument("--disable-extensions")
    chrome.add_argument("--disable-sync")
    chrome.add_argument("--metrics-recording-only")
    chrome.add_argument("--no-first-run")
    chrome.add_argument("--safebrowsing-disable-auto-update")
    chrome.add_argument(f"--window-size={options.window_width},{options.window_height}")
    chrome.add_argument(f"--proxy-server={options.proxy_url}")
    chrome.add_argument("--proxy-bypass-list=<-loopback>")
    # Force all hostnames through the validating proxy (which resolves and
    # pins the address) instead of letting Chrome resolve DNS itself. The
    # proxy hostname itself must stay resolvable for Chrome to reach it. Remove
    # Chrome's implicit loopback bypass so local destinations reach that proxy.
    proxy_host = urlsplit(options.proxy_url).hostname or ""
    if proxy_host:
        chrome.add_argument(f"--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE {proxy_host}")
    else:
        chrome.add_argument("--host-resolver-rules=MAP * ~NOTFOUND")
    chrome.set_capability("pageLoadStrategy", "normal")
    return chrome


def create_driver(options: BrowserOptions, settings: Settings) -> webdriver.Remote:
    chrome = build_chrome_options(options)
    if settings.selenium_remote_url:
        driver = webdriver.Remote(
            command_executor=settings.selenium_remote_url,
            options=chrome,
        )
    else:
        driver = webdriver.Chrome(options=chrome)
    driver.set_page_load_timeout(options.page_load_timeout)
    driver.set_script_timeout(options.page_load_timeout)
    return driver


def register_session(settings: Settings, *, job_id: uuid.UUID, session_id: str) -> None:
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        client.set(
            SESSION_KEY.format(job_id=job_id),
            session_id,
            ex=settings.session_registry_ttl_seconds,
        )
    finally:
        client.close()


def clear_session(settings: Settings, *, job_id: uuid.UUID) -> None:
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        client.delete(SESSION_KEY.format(job_id=job_id))
    finally:
        client.close()


class SessionWatchdog:
    """Quit a browser session if the job deadline is reached."""

    def __init__(self, driver: webdriver.Remote, timeout: float) -> None:
        self._driver = driver
        self._timeout = max(1.0, timeout)
        self._timer: threading.Timer | None = None
        self.fired = False

    def __enter__(self) -> SessionWatchdog:
        self._timer = threading.Timer(self._timeout, self._fire)
        self._timer.daemon = True
        self._timer.start()
        return self

    def _fire(self) -> None:
        self.fired = True
        with contextlib.suppress(Exception):
            self._driver.quit()

    def __exit__(self, *exc_info: object) -> None:
        if self._timer is not None:
            self._timer.cancel()


def load_page(
    driver: webdriver.Remote,
    *,
    url: str,
    wait_for: str | None,
    timeout: float,
) -> tuple[str, str]:
    driver.get(url)
    if wait_for:
        WebDriverWait(driver, timeout).until(
            expected_conditions.presence_of_element_located(("css selector", wait_for))
        )
    return str(driver.current_url), str(driver.page_source)


def screenshot(driver: webdriver.Remote) -> bytes:
    return bytes(driver.get_screenshot_as_png())
