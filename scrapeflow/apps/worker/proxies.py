"""Per-job proxy assignment, health checks, and retry bookkeeping."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog
from packages.core.errors import AppError, ErrorCode
from packages.core.proxies import ProxyEndpoint
from packages.core.settings import Settings
from redis.asyncio import Redis

from apps.worker.providers import build_provider
from apps.worker.providers.base import ProxyProvider

logger = structlog.get_logger(__name__)

Probe = Callable[[ProxyEndpoint, float], Awaitable[bool]]

_ROUND_ROBIN_KEY = "sf:proxy:rr:{provider}"
_HEALTHY_KEY = "sf:proxy:healthy:{endpoint}"
_DOWN_KEY = "sf:proxy:down:{endpoint}"


@dataclass(frozen=True, slots=True)
class ProxyLease:
    """The upstream proxy assigned to one job attempt."""

    endpoint: ProxyEndpoint

    @property
    def id(self) -> str:
        return self.endpoint.id

    @property
    def url(self) -> str:
        return self.endpoint.url


def proxy_metadata(lease: ProxyLease | None) -> dict[str, str | None] | None:
    """Describe a lease without ever exposing credentials."""
    if lease is None:
        return None
    return {
        "id": lease.endpoint.id,
        "provider": lease.endpoint.provider,
        "country": lease.endpoint.country,
    }


def ensure_browser_egress(settings: Settings, *, render_js: bool) -> None:
    """Refuse browser jobs whose egress proxy Grid cannot reach.

    A remote Grid cannot use a loopback proxy. With per-job proxies the worker
    starts a local validating proxy, so operators must advertise a reachable
    worker host. Without per-job proxies the shared egress proxy is required.
    """
    if not render_js or not settings.selenium_remote_url:
        return
    if settings.proxy_enabled:
        advertised = settings.egress_job_proxy_advertise_host
        if advertised is None or _is_loopback(advertised):
            raise AppError(
                503,
                ErrorCode.SERVICE_UNAVAILABLE,
                "Per-job proxies with remote Grid require a reachable "
                "EGRESS_JOB_PROXY_ADVERTISE_HOST",
            )
        return
    if not settings.egress_proxy_url:
        raise AppError(
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "Browser jobs require EGRESS_PROXY_URL so Grid traffic is validated",
        )


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() in {"localhost", "localhost.localdomain"}


class ProxyAllocator:
    """Choose healthy proxies and remember failures for the next attempt.

    State is shared through Redis so two workers do not hammer a proxy that is
    known to be down. Health probes are cached briefly to avoid a TCP connect on
    every job; failures place the endpoint in a longer cooldown.
    """

    def __init__(
        self,
        settings: Settings,
        redis: Redis | None,
        *,
        provider: ProxyProvider | None = None,
        probe: Probe | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis
        self._provider = provider
        if settings.proxy_enabled and self._provider is None:
            self._provider = build_provider(settings)
        self._probe = probe or _tcp_probe
        self._used: set[str] = set()

    async def acquire(self, country: str | None) -> ProxyLease | None:
        """Return the next healthy lease, or ``None`` when proxies are disabled."""
        if not self._settings.proxy_enabled:
            if country is not None:
                raise AppError(
                    422,
                    ErrorCode.VALIDATION_ERROR,
                    f"Proxy country {country} is not available",
                )
            return None
        if self._provider is None:  # pragma: no cover - settings validator
            raise AppError(
                503,
                ErrorCode.SERVICE_UNAVAILABLE,
                "Proxy provider is not configured",
            )
        candidates = self._provider.candidates(country)
        if not candidates:
            raise AppError(
                422,
                ErrorCode.VALIDATION_ERROR,
                f"Proxy country {country} is not available",
            )
        unused = [endpoint for endpoint in candidates if endpoint.id not in self._used]
        pool = unused or list(candidates)
        start = await self._next_index(len(pool))
        ordered = [*pool[start:], *pool[:start]]
        for endpoint in ordered:
            if await self._healthy(endpoint):
                self._used.add(endpoint.id)
                logger.info(
                    "proxy.assigned",
                    proxy_id=endpoint.id,
                    provider=endpoint.provider,
                    country=endpoint.country,
                )
                return ProxyLease(endpoint)
        raise AppError(
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "No healthy proxy is available",
        )

    async def report_success(self, lease: ProxyLease) -> None:
        if self._redis is None:  # pragma: no cover - only enabled jobs use this
            return
        await self._redis.delete(_DOWN_KEY.format(endpoint=lease.endpoint.id))
        logger.info(
            "proxy.succeeded",
            proxy_id=lease.endpoint.id,
            provider=lease.endpoint.provider,
            country=lease.endpoint.country,
        )

    async def report_failure(self, lease: ProxyLease) -> None:
        if self._redis is None:  # pragma: no cover - only enabled jobs use this
            return
        await self._mark_down(lease.endpoint)
        logger.warning(
            "proxy.failed",
            proxy_id=lease.endpoint.id,
            provider=lease.endpoint.provider,
            country=lease.endpoint.country,
        )

    async def _healthy(self, endpoint: ProxyEndpoint) -> bool:
        if self._redis is None:  # pragma: no cover - only enabled jobs use this
            return True
        down_key = _DOWN_KEY.format(endpoint=endpoint.id)
        if await self._redis.exists(down_key):
            return False
        if not self._settings.proxy_health_check_enabled:
            return True
        healthy_key = _HEALTHY_KEY.format(endpoint=endpoint.id)
        if await self._redis.exists(healthy_key):
            return True
        try:
            healthy = await self._probe(
                endpoint,
                self._settings.proxy_health_timeout_seconds,
            )
        except Exception:  # pragma: no cover - probes should not raise
            healthy = False
        if healthy:
            await self._redis.set(
                healthy_key,
                "1",
                ex=self._settings.proxy_health_cache_seconds,
            )
            return True
        await self._mark_down(endpoint)
        logger.warning(
            "proxy.health_check_failed",
            proxy_id=endpoint.id,
            provider=endpoint.provider,
            country=endpoint.country,
        )
        return False

    async def _mark_down(self, endpoint: ProxyEndpoint) -> None:
        if self._redis is None:  # pragma: no cover - only enabled jobs use this
            return
        await self._redis.set(
            _DOWN_KEY.format(endpoint=endpoint.id),
            "1",
            ex=self._settings.proxy_health_cooldown_seconds,
        )
        await self._redis.delete(_HEALTHY_KEY.format(endpoint=endpoint.id))

    async def _next_index(self, size: int) -> int:
        if self._redis is None:  # pragma: no cover - only enabled jobs use this
            return 0
        provider_name = self._provider.name if self._provider is not None else "unknown"
        value: Any = await self._redis.incr(_ROUND_ROBIN_KEY.format(provider=provider_name))
        return (int(value) - 1) % max(1, size)


async def _tcp_probe(endpoint: ProxyEndpoint, budget_seconds: float) -> bool:
    """TCP reachability probe; never sends credentials or target traffic."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(endpoint.host, endpoint.port),
            timeout=budget_seconds,
        )
    except (OSError, TimeoutError, ValueError):
        return False
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()
    return True
