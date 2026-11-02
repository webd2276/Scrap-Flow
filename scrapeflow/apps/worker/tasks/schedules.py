"""Beat task that dispatches due cron schedules."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from packages.core.settings import Settings, get_settings
from redis.asyncio import Redis

from apps.worker.celery_app import celery_app
from apps.worker.schedules import DISPATCH_LOCK, dispatch_due_schedules

logger = structlog.get_logger(__name__)

_RELEASE_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


async def _dispatch(settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    token = uuid.uuid4().hex
    lock_seconds = max(30, settings.schedule_dispatch_interval_seconds * 2)
    acquired = await redis.set(DISPATCH_LOCK, token, nx=True, ex=lock_seconds)
    if not acquired:
        await redis.aclose()
        return {"dispatched": 0, "skipped": 0, "due": 0}
    try:
        return await dispatch_due_schedules(settings=settings, redis=redis)
    finally:
        try:
            await redis.eval(_RELEASE_LOCK, 1, DISPATCH_LOCK, token)
        finally:
            await redis.aclose()


@celery_app.task(name="scrapeflow.dispatch_schedules")  # type: ignore[untyped-decorator]
def dispatch_schedules() -> dict[str, int]:
    return asyncio.run(_dispatch())
