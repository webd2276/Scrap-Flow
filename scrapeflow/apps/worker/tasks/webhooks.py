"""Beat task that drains the signed-webhook outbox."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from packages.core.settings import Settings, get_settings
from redis.asyncio import Redis

from apps.worker.celery_app import celery_app
from apps.worker.webhooks import DELIVERY_LOCK, deliver_pending

logger = structlog.get_logger(__name__)

_RELEASE_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


async def _deliver(settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    token = uuid.uuid4().hex
    lock_seconds = max(30, settings.webhook_dispatch_interval_seconds * 2)
    acquired = await redis.set(DELIVERY_LOCK, token, nx=True, ex=lock_seconds)
    if not acquired:
        await redis.aclose()
        return {"sent": 0, "retrying": 0, "dead": 0}
    try:
        return await deliver_pending(settings=settings)
    finally:
        try:
            await redis.eval(_RELEASE_LOCK, 1, DELIVERY_LOCK, token)
        finally:
            await redis.aclose()


@celery_app.task(name="scrapeflow.deliver_webhooks")  # type: ignore[untyped-decorator]
def deliver_webhooks() -> dict[str, int]:
    return asyncio.run(_deliver())
