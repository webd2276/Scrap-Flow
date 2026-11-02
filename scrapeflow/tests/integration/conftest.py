from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import asyncpg
import packages.core.models  # noqa: F401 - register metadata
import pytest
from apps.api.main import create_app
from fastapi.testclient import TestClient
from packages.core.db import Base
from packages.core.settings import Settings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

TRUNCATE_SQL = """
TRUNCATE TABLE stripe_events, usage_ledger, job_events, artifacts, jobs, audit_logs,
  refresh_tokens, api_keys, memberships, users, organizations
RESTART IDENTITY CASCADE
"""


class RecordingDispatcher:
    def __init__(self) -> None:
        self.enqueued: list[uuid.UUID] = []

    def enqueue(self, job_id: uuid.UUID) -> bool:
        self.enqueued.append(job_id)
        return True


class OkProbe:
    name = "ok"

    async def check(self) -> None:
        return None


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} not set; integration services unavailable")
    return value


@pytest.fixture(scope="session")
def database_url() -> str:
    value = _env("TEST_DATABASE_URL")
    assert value is not None
    return value


@pytest.fixture(scope="session")
def redis_url() -> str:
    value = _env("TEST_REDIS_URL")
    assert value is not None
    return value


@pytest.fixture(scope="session", autouse=True)
def _schema(database_url: str) -> None:
    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(reset())


@pytest.fixture
def integration_settings(database_url: str, redis_url: str, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        redis_url=redis_url,
        api_key_pepper="a" * 40,
        jwt_secret="b" * 40,
        webhook_secret_key="c" * 40,
        cors_origins="http://localhost:3000",
        rate_limit_auth_burst=100,
        rate_limit_auth_per_minute=100,
        rate_limit_ip_burst=1000,
        rate_limit_ip_per_minute=1000,
        rate_limit_org_burst=1000,
        rate_limit_org_per_minute=1000,
        artifacts_local_dir=str(tmp_path / "artifacts"),
    )


@pytest.fixture(autouse=True)
def _clean(integration_settings: Settings) -> Iterator[None]:
    async def clean() -> None:
        connection = await asyncpg.connect(integration_settings.asyncpg_dsn)
        try:
            await connection.execute(TRUNCATE_SQL)
        finally:
            await connection.close()
        redis = Redis.from_url(integration_settings.redis_url, decode_responses=True)
        try:
            await redis.flushdb()
        finally:
            await redis.aclose()

    asyncio.run(clean())
    yield


@pytest.fixture
def dispatcher() -> RecordingDispatcher:
    return RecordingDispatcher()


@pytest.fixture
def client(integration_settings: Settings, dispatcher: RecordingDispatcher) -> Iterator[TestClient]:
    app = create_app(integration_settings, probes=[OkProbe()], dispatcher=dispatcher)
    with TestClient(app) as test_client:
        yield test_client


def signup_payload(email: str = "owner@example.com", org: str = "Acme") -> dict[str, Any]:
    return {
        "org_name": org,
        "email": email,
        "password": "correct horse battery",
        "display_name": "Owner",
        "tos_accepted": True,
    }


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
