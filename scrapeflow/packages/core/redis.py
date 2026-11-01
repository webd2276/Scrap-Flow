"""Redis client construction and request dependency."""

from __future__ import annotations

from typing import cast

from fastapi import Request
from redis.asyncio import Redis

from packages.core.settings import Settings


def create_redis(settings: Settings) -> Redis:
    return cast(
        Redis,
        Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        ),
    )


def get_redis(request: Request) -> Redis:
    client: Redis = request.app.state.redis
    return client
