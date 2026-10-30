from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from apps.api.main import create_app
from fastapi.testclient import TestClient
from packages.core.settings import Settings


class OkProbe:
    name = "ok"

    async def check(self) -> None:
        return None


class FailingProbe:
    name = "broken"

    async def check(self) -> None:
        raise RuntimeError("dependency down")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://scrapeflow:scrapeflow@localhost:5432/scrapeflow",
        redis_url="redis://localhost:6379/0",
        api_key_pepper="a" * 40,
        jwt_secret="b" * 40,
        webhook_secret_key="c" * 40,
        cors_origins="http://localhost:3000",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, probes=[OkProbe()])
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def failing_client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, probes=[FailingProbe()])
    with TestClient(app) as test_client:
        yield test_client


def envelope(response: Any) -> dict[str, Any]:
    body: dict[str, Any] = response.json()
    return body
