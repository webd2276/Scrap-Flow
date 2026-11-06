from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from apps.worker.providers.base import CatalogProxyProvider
from apps.worker.proxies import (
    ProxyAllocator,
    ProxyLease,
    ensure_browser_egress,
    proxy_metadata,
)
from packages.core.errors import AppError, ErrorCode
from packages.core.proxies import ProxyCatalog, ProxyEndpoint
from packages.core.settings import Settings


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int | str] = {}
        self.expiries: dict[str, int | None] = {}

    async def exists(self, key: str) -> int:
        return 1 if key in self.values else 0

    async def set(self, key: str, value: object, *, ex: int | None = None) -> bool:
        self.values[key] = str(value)
        self.expiries[key] = ex
        return True

    async def delete(self, key: str) -> int:
        self.expiries.pop(key, None)
        return 1 if self.values.pop(key, None) is not None else 0

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "api_key_pepper": "a" * 40,
        "jwt_secret": "b" * 40,
        "webhook_secret_key": "c" * 40,
        "artifacts_local_dir": str(tmp_path),
        "proxy_enabled": True,
        "proxy_static_list": (
            "DE|http://user:secret@de-one.proxy:8080,DE|http://user:secret@de-two.proxy:8080"
        ),
        "proxy_health_check_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _catalog(*, countries: tuple[str, ...] = ("DE", "US")) -> ProxyCatalog:
    endpoints = tuple(
        ProxyEndpoint(
            id=f"static-{country.lower()}-{index}",
            provider="static",
            country=country,
            url=f"http://user:secret@{country.lower()}-{index}.proxy:8080",
        )
        for country in countries
        for index in (1, 2)
    )
    return ProxyCatalog("static", endpoints, frozenset(countries))


def _allocator(
    settings: Settings,
    redis: FakeRedis | None,
    *,
    catalog: ProxyCatalog | None = None,
    probe: Any = None,
) -> ProxyAllocator:
    return ProxyAllocator(
        settings,
        redis,  # type: ignore[arg-type]
        provider=CatalogProxyProvider(catalog or _catalog()),
        probe=probe,
    )


@pytest.mark.asyncio
async def test_disabled_allocator_rejects_country_and_returns_none(tmp_path: Path) -> None:
    allocator = _allocator(_settings(tmp_path, proxy_enabled=False), None)
    assert await allocator.acquire(None) is None
    with pytest.raises(AppError) as exc:
        await allocator.acquire("DE")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_allocator_selects_country_and_rotates(tmp_path: Path) -> None:
    redis = FakeRedis()
    allocator = _allocator(_settings(tmp_path), redis)

    first = await allocator.acquire("DE")
    second = await allocator.acquire("DE")
    assert first is not None and second is not None
    assert first.id != second.id
    assert first.endpoint.country == "DE"

    with pytest.raises(AppError) as exc:
        await allocator.acquire("FR")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_allocator_health_failover_and_cooldown(tmp_path: Path) -> None:
    redis = FakeRedis()
    seen: list[str] = []

    async def probe(endpoint: ProxyEndpoint, budget_seconds: float) -> bool:
        seen.append(endpoint.id)
        return endpoint.id != "static-de-1"

    settings = _settings(tmp_path, proxy_health_check_enabled=True)
    allocator = _allocator(settings, redis, probe=probe)
    lease = await allocator.acquire("DE")
    assert lease is not None
    assert lease.id == "static-de-2"
    assert "static-de-1" in seen
    assert await redis.exists("sf:proxy:down:static-de-1") == 1


@pytest.mark.asyncio
async def test_failed_lease_is_not_reused_and_all_down_is_503(tmp_path: Path) -> None:
    redis = FakeRedis()
    allocator = _allocator(_settings(tmp_path), redis)
    first = await allocator.acquire("DE")
    assert first is not None
    await allocator.report_failure(first)
    second = await allocator.acquire("DE")
    assert second is not None
    assert second.id != first.id

    await allocator.report_failure(second)
    with pytest.raises(AppError) as exc:
        await allocator.acquire("DE")
    assert exc.value.code == ErrorCode.SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_health_probe_failure_marks_endpoint_down(tmp_path: Path) -> None:
    redis = FakeRedis()

    async def probe(endpoint: ProxyEndpoint, budget_seconds: float) -> bool:
        return False

    settings = _settings(tmp_path, proxy_health_check_enabled=True)
    allocator = _allocator(settings, redis, probe=probe)
    with pytest.raises(AppError) as exc:
        await allocator.acquire("DE")
    assert exc.value.code == ErrorCode.SERVICE_UNAVAILABLE
    assert await redis.exists("sf:proxy:down:static-de-1") == 1


def test_proxy_metadata_never_contains_credentials(tmp_path: Path) -> None:
    lease = ProxyLease(
        ProxyEndpoint(
            id="static-de",
            provider="static",
            country="DE",
            url="http://user:super-secret@de.proxy:8080",
        )
    )
    metadata = proxy_metadata(lease)
    assert metadata == {"id": "static-de", "provider": "static", "country": "DE"}
    assert "super-secret" not in repr(metadata)
    assert proxy_metadata(None) is None


def test_ensure_browser_egress_requires_reachable_proxy(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        proxy_enabled=False,
        selenium_remote_url="http://grid:4444",
        egress_proxy_url=None,
    )
    with pytest.raises(AppError) as exc:
        ensure_browser_egress(settings, render_js=True)
    assert exc.value.code == ErrorCode.SERVICE_UNAVAILABLE

    shared = settings.model_copy(update={"egress_proxy_url": "http://egress:8888"})
    ensure_browser_egress(shared, render_js=True)

    per_job = _settings(tmp_path, selenium_remote_url="http://grid:4444")
    with pytest.raises(AppError) as exc:
        ensure_browser_egress(per_job, render_js=True)
    assert "EGRESS_JOB_PROXY_ADVERTISE_HOST" in exc.value.message

    advertised = per_job.model_copy(
        update={
            "egress_job_proxy_bind_host": "0.0.0.0",  # noqa: S104
            "egress_job_proxy_advertise_host": "worker",
        }
    )
    ensure_browser_egress(advertised, render_js=True)
    ensure_browser_egress(per_job, render_js=False)
