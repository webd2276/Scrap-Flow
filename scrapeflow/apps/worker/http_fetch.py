"""HTTP fetching for ``render_js=false`` jobs.

The fetcher validates every hop, never follows redirects on its own, and routes
traffic through the validating egress proxy so DNS is resolved twice and the
connection is pinned to the checked address.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from packages.core.errors import AppError, ErrorCode
from packages.core.ssrf import Resolver, SSRFPolicy, validate_redirect, validate_url

CancelCheck = Callable[[], Awaitable[bool]]


class JobCancelledError(Exception):
    """Raised cooperatively when a running job is cancelled."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status_code: int
    content: bytes
    content_type: str
    headers: dict[str, str]
    redirects: tuple[str, ...]


async def _check_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and await cancel_check():
        raise JobCancelledError


async def fetch_url(
    url: str,
    *,
    policy: SSRFPolicy,
    proxy_url: str,
    timeout_seconds: float,
    max_bytes: int,
    max_redirects: int,
    user_agent: str,
    headers: dict[str, str] | None = None,
    cancel_check: CancelCheck | None = None,
    resolver: Resolver | None = None,
) -> FetchResult:
    await _check_cancelled(cancel_check)
    current = await validate_url(url, policy, resolver)
    chain: list[str] = []
    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))

    request_headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        **(headers or {}),
    }

    async with httpx.AsyncClient(
        proxy=proxy_url,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        headers=request_headers,
    ) as client:
        for _ in range(max_redirects + 1):
            await _check_cancelled(cancel_check)
            try:
                async with client.stream("GET", current.url) as response:
                    if response.headers.get("x-scrapeflow-proxy-error") == "1":
                        body = await response.aread()
                        message = body.decode("utf-8", "replace")[:300]
                        status = (
                            ErrorCode.BLOCKED_URL
                            if response.status_code in {400, 403, 444}
                            else ErrorCode.UPSTREAM_ERROR
                        )
                        raise AppError(
                            422 if status == ErrorCode.BLOCKED_URL else 502,
                            status,
                            message or "Egress request was rejected",
                        )

                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise AppError(
                                502,
                                ErrorCode.UPSTREAM_ERROR,
                                "Redirect response had no Location header",
                            )
                        next_url = validate_redirect(current, location, policy)
                        # Validate the next hop before touching the network.
                        current = await validate_url(next_url, policy, resolver)
                        chain.append(current.url)
                        continue

                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > max_bytes:
                            raise AppError(
                                422,
                                ErrorCode.UPSTREAM_ERROR,
                                f"Response exceeds the {max_bytes} byte limit",
                            )
                        content.extend(chunk)
                        await _check_cancelled(cancel_check)
                    return FetchResult(
                        url=str(response.url),
                        status_code=response.status_code,
                        content=bytes(content),
                        content_type=response.headers.get("content-type", ""),
                        headers=dict(response.headers),
                        redirects=tuple(chain),
                    )
            except httpx.TimeoutException as exc:
                raise AppError(504, ErrorCode.TIMEOUT, "Upstream request timed out") from exc
            except httpx.HTTPError as exc:
                raise AppError(502, ErrorCode.UPSTREAM_ERROR, "Upstream request failed") from exc

    raise AppError(
        502,
        ErrorCode.UPSTREAM_ERROR,
        f"Too many redirects (limit {max_redirects})",
    )


def absolute_links(html_links: list[str], base_url: str) -> list[str]:
    return [urljoin(base_url, link) for link in html_links]
