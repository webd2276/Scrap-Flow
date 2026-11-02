"""Worker-side access to staged automation secrets.

The worker reads the sealed map once per job and deletes it when the job ends.
Redis is synchronous here because the read happens before the browser thread
starts and the TTL is the only durable guarantee we need.
"""

from __future__ import annotations

import uuid
from typing import cast

import redis
from packages.core.errors import AppError, ErrorCode
from packages.core.secretbox import SecretBoxError, encryption_key, open_secrets
from packages.core.settings import Settings

SECRETS_KEY = "sf:automation:secrets:{job_id}"


def _key(job_id: uuid.UUID) -> str:
    return SECRETS_KEY.format(job_id=job_id)


def load_secrets(settings: Settings, job_id: uuid.UUID) -> dict[str, str]:
    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        token = cast(str | None, client.get(_key(job_id)))
    finally:
        client.close()
    if token is None:
        return {}
    try:
        return open_secrets(
            token,
            key=encryption_key(settings),
            associated_data=str(job_id).encode("ascii"),
        )
    except SecretBoxError as exc:
        raise AppError(
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "Staged secret material is unavailable",
            details={"retryable": False},
        ) from exc


def delete_secrets(settings: Settings, job_id: uuid.UUID) -> None:
    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        client.delete(_key(job_id))
    finally:
        client.close()
