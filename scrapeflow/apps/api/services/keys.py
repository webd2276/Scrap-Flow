"""API key lifecycle services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from packages.core.errors import AppError, ErrorCode
from packages.core.models import ApiKey
from packages.core.security import generate_api_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_KEYS_PER_ORG = 50


async def create_key(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    name: str,
    scopes: list[str],
    created_by: uuid.UUID | None,
    pepper: str,
    expires_at: datetime | None,
) -> tuple[ApiKey, str]:
    active = (
        await db.execute(
            select(ApiKey.id).where(ApiKey.org_id == org_id, ApiKey.revoked_at.is_(None))
        )
    ).all()
    if len(active) >= MAX_KEYS_PER_ORG:
        raise AppError(
            409,
            ErrorCode.CONFLICT,
            f"Active key limit reached ({MAX_KEYS_PER_ORG}); revoke an old key first",
        )

    generated = generate_api_key(pepper)
    key = ApiKey(
        org_id=org_id,
        name=name.strip(),
        prefix=generated.prefix,
        key_hash=generated.key_hash,
        scopes=scopes,
        created_by=created_by,
        expires_at=expires_at,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return key, generated.plaintext


async def list_keys(db: AsyncSession, org_id: uuid.UUID) -> list[ApiKey]:
    return list(
        (
            await db.execute(
                select(ApiKey).where(ApiKey.org_id == org_id).order_by(ApiKey.created_at.desc())
            )
        ).scalars()
    )


async def revoke_key(db: AsyncSession, *, org_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey:
    key = await db.get(ApiKey, key_id)
    if key is None or key.org_id != org_id:
        raise AppError(404, ErrorCode.NOT_FOUND, "API key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(key)
    return key
