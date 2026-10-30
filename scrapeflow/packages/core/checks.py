"""Dependency probes for the readiness endpoint."""

from __future__ import annotations

import asyncio
from typing import Protocol

import asyncpg
from redis.asyncio import Redis

from packages.core.settings import Settings


class ReadinessProbe(Protocol):
    name: str

    async def check(self) -> None: ...


class PostgresProbe:
    name = "postgres"

    def __init__(self, dsn: str, timeout: float = 2.0) -> None:
        self._dsn = dsn
        self._timeout = timeout

    async def check(self) -> None:
        connection = await asyncpg.connect(self._dsn, timeout=self._timeout)
        try:
            await connection.execute("SELECT 1")
        finally:
            await connection.close()


class RedisProbe:
    name = "redis"

    def __init__(self, url: str, timeout: float = 2.0) -> None:
        self._url = url
        self._timeout = timeout

    async def check(self) -> None:
        client = Redis.from_url(self._url, socket_connect_timeout=self._timeout)
        try:
            await client.ping()
        finally:
            await client.aclose()  # type: ignore[attr-defined]


def build_default_probes(settings: Settings) -> list[ReadinessProbe]:
    return [
        PostgresProbe(settings.asyncpg_dsn, settings.readiness_timeout_seconds),
        RedisProbe(settings.redis_url, settings.readiness_timeout_seconds),
    ]


async def run_probes(probes: list[ReadinessProbe], timeout_s: float) -> dict[str, dict[str, str]]:
    """Run all probes concurrently; never raises."""

    async def one(probe: ReadinessProbe) -> tuple[str, dict[str, str]]:
        try:
            await asyncio.wait_for(probe.check(), timeout=timeout_s)
        except TimeoutError:
            return probe.name, {"status": "error", "reason": "timeout"}
        except Exception as exc:
            return probe.name, {"status": "error", "reason": type(exc).__name__}
        return probe.name, {"status": "ok"}

    results = await asyncio.gather(*(one(probe) for probe in probes))
    return dict(results)
