"""Transient storage for automation secret values.

Only ciphertext is written to Redis, keyed by job id and bound to that id via
AES-GCM associated data. The worker deletes the key when execution ends.
"""

from __future__ import annotations

import uuid

from packages.core.secretbox import encryption_key, seal_secrets
from packages.core.settings import Settings
from redis.asyncio import Redis

SECRETS_KEY = "sf:automation:secrets:{job_id}"


def secrets_key(job_id: uuid.UUID) -> str:
    return SECRETS_KEY.format(job_id=job_id)


async def store_secrets(
    redis: Redis,
    settings: Settings,
    job_id: uuid.UUID,
    secrets: dict[str, str],
) -> None:
    if not secrets:
        return
    token = seal_secrets(
        secrets,
        key=encryption_key(settings),
        associated_data=str(job_id).encode("ascii"),
    )
    await redis.set(
        secrets_key(job_id),
        token,
        ex=settings.automation_secrets_ttl_seconds,
    )


async def delete_secrets(redis: Redis, job_id: uuid.UUID) -> None:
    await redis.delete(secrets_key(job_id))
