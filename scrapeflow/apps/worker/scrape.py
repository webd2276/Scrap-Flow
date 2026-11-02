"""Scrape execution shared by the Celery task."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import Any

import structlog
from packages.core.artifacts import ArtifactStore, StoredArtifact
from packages.core.errors import AppError, ErrorCode
from packages.core.models import Job
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy, validate_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.schemas.scrape import ScrapeRequest
from apps.worker.browser.runner import run_browser_page
from apps.worker.egress_proxy import ProxyConfig, running_proxy
from apps.worker.extract import extract_page, find_next_url
from apps.worker.http_fetch import JobCancelledError, fetch_url
from apps.worker.job_store import cancel_requested

logger = structlog.get_logger(__name__)

_CHARSET = re.compile(r"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)", re.IGNORECASE)


def _decode_body(content: bytes, content_type: str) -> str:
    match = _CHARSET.search(content_type)
    encoding = match.group(1) if match else "utf-8"
    try:
        return content.decode(encoding, "replace")
    except LookupError:
        return content.decode("utf-8", "replace")


@dataclass(frozen=True, slots=True)
class ProducedArtifact:
    kind: str
    filename: str
    content_type: str
    data: bytes
    stored: StoredArtifact


@dataclass(frozen=True, slots=True)
class ScrapeOutcome:
    result: dict[str, Any]
    artifacts: tuple[ProducedArtifact, ...]


class CancelWatcher:
    """Cheap, throttled cancellation polling so fetches can stop early."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        job_id: uuid.UUID,
        interval: float = 1.0,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._job_id = job_id
        self._interval = interval
        self._next_check = 0.0

    async def __call__(self) -> bool:
        now = time.monotonic()
        if now < self._next_check:
            return False
        self._next_check = now + self._interval
        async with self._sessionmaker() as session:
            return await cancel_requested(session, self._job_id)


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AppError(504, ErrorCode.TIMEOUT, "Job exceeded its deadline")
    return remaining


@asynccontextmanager
async def egress_proxy(settings: Settings, policy: SSRFPolicy) -> AsyncIterator[str]:
    if settings.egress_proxy_url:
        yield settings.egress_proxy_url
        return
    config = ProxyConfig(
        policy=policy,
        connect_timeout=settings.egress_connect_timeout_seconds,
        idle_timeout=settings.egress_idle_timeout_seconds,
        max_header_bytes=settings.egress_max_header_bytes,
    )
    async with running_proxy(config) as url:
        yield url


def _build_artifacts(
    *,
    settings: Settings,
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    result: dict[str, Any],
    screenshot_png: bytes | None,
    html: str | None,
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
    if screenshot_png is not None:
        produced.append(
            ProducedArtifact(
                kind="screenshot",
                filename="screenshot.png",
                content_type="image/png",
                data=screenshot_png,
                stored=store.put(
                    org_id=org_id,
                    job_id=job_id,
                    filename="screenshot.png",
                    content_type="image/png",
                    data=screenshot_png,
                ),
            )
        )
    return tuple(produced)


async def _fetch_pages_http(
    scrape: ScrapeRequest,
    *,
    settings: Settings,
    policy: SSRFPolicy,
    proxy_url: str,
    deadline: float,
    cancel: CancelWatcher,
) -> tuple[list[dict[str, Any]], list[str], bytes | None]:
    pages: list[dict[str, Any]] = []
    redirects: list[str] = []
    first_html: bytes | None = None
    seen = {scrape.url}
    max_pages = scrape.pagination.max_pages if scrape.pagination else 1
    current = scrape.url
    for index in range(max_pages):
        remaining = _remaining(deadline)
        fetched = await fetch_url(
            current,
            policy=policy,
            proxy_url=proxy_url,
            timeout_seconds=min(remaining, settings.http_timeout_seconds),
            max_bytes=settings.http_max_bytes,
            max_redirects=settings.http_max_redirects,
            user_agent=settings.http_user_agent,
            headers=scrape.headers,
            cancel_check=cancel,
        )
        if index == 0:
            redirects = list(fetched.redirects)
            first_html = fetched.content
        html = _decode_body(fetched.content, fetched.content_type)
        page = extract_page(
            html,
            base_url=fetched.url,
            options=scrape.extract,
            selectors=scrape.selectors,
        )
        page["url"] = fetched.url
        page["status_code"] = fetched.status_code
        page["content_type"] = fetched.content_type
        pages.append(page)
        if scrape.pagination is None:
            break
        next_url = find_next_url(
            html,
            base_url=fetched.url,
            spec=scrape.pagination.next_selector,
        )
        if not next_url or next_url in seen:
            break
        seen.add(next_url)
        current = next_url
    return pages, redirects, first_html


async def _fetch_pages_browser(
    scrape: ScrapeRequest,
    *,
    settings: Settings,
    policy: SSRFPolicy,
    proxy_url: str,
    deadline: float,
    cancel: CancelWatcher,
    job_id: uuid.UUID,
) -> tuple[list[dict[str, Any]], list[str], bytes | None, str | None]:
    pages: list[dict[str, Any]] = []
    redirects: list[str] = []
    first_html: str | None = None
    screenshot_png: bytes | None = None
    seen = {scrape.url}
    max_pages = scrape.pagination.max_pages if scrape.pagination else 1
    current = scrape.url
    for index in range(max_pages):
        if await cancel():
            raise JobCancelledError
        remaining = _remaining(deadline)
        try:
            browser_result = await asyncio.wait_for(
                asyncio.to_thread(
                    partial(
                        run_browser_page,
                        settings=settings,
                        job_id=job_id,
                        url=current,
                        wait_for=scrape.wait_for,
                        timeout_seconds=remaining,
                        proxy_url=proxy_url,
                        take_screenshot=scrape.screenshot,
                    )
                ),
                timeout=remaining + 5,
            )
        except TimeoutError as exc:
            raise AppError(504, ErrorCode.TIMEOUT, "Browser job exceeded its deadline") from exc
        final = await validate_url(browser_result.final_url, policy)
        html = browser_result.html
        if final.url != current:
            redirects.append(final.url)
        if index == 0:
            first_html = html
            screenshot_png = browser_result.screenshot_png
        page = extract_page(
            html,
            base_url=final.url,
            options=scrape.extract,
            selectors=scrape.selectors,
        )
        page["url"] = final.url
        page["status_code"] = None
        pages.append(page)
        if scrape.pagination is None:
            break
        next_url = find_next_url(
            html,
            base_url=final.url,
            spec=scrape.pagination.next_selector,
        )
        if not next_url or next_url in seen:
            break
        seen.add(next_url)
        current = next_url
    return pages, redirects, screenshot_png, first_html


async def execute_scrape(
    *,
    job: Job,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    deadline: float,
    policy: SSRFPolicy | None = None,
) -> ScrapeOutcome:
    scrape = ScrapeRequest.model_validate(job.payload)
    policy = policy or SSRFPolicy(allowed_ports=settings.egress_port_set)
    cancel = CancelWatcher(sessionmaker, job.id)
    started = time.monotonic()

    if scrape.render_js and settings.selenium_remote_url and not settings.egress_proxy_url:
        raise AppError(
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "Browser jobs require EGRESS_PROXY_URL so Grid traffic is validated",
        )

    async with egress_proxy(settings, policy) as proxy_url:
        if scrape.render_js:
            pages, redirects, screenshot_png, first_html = await _fetch_pages_browser(
                scrape,
                settings=settings,
                policy=policy,
                proxy_url=proxy_url,
                deadline=deadline,
                cancel=cancel,
                job_id=job.id,
            )
            html_artifact = first_html if scrape.include_html else None
        else:
            pages, redirects, first_html_bytes = await _fetch_pages_http(
                scrape,
                settings=settings,
                policy=policy,
                proxy_url=proxy_url,
                deadline=deadline,
                cancel=cancel,
            )
            screenshot_png = None
            html_artifact = (
                first_html_bytes.decode("utf-8", "replace")
                if scrape.include_html and first_html_bytes is not None
                else None
            )

    result: dict[str, Any] = dict(pages[0])
    result["render_js"] = scrape.render_js
    result["redirects"] = redirects
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    if scrape.pagination is not None:
        result["pages"] = pages

    artifacts = await asyncio.to_thread(
        _build_artifacts,
        settings=settings,
        org_id=job.org_id,
        job_id=job.id,
        result=result,
        screenshot_png=screenshot_png,
        html=html_artifact,
    )
    return ScrapeOutcome(result=result, artifacts=artifacts)
