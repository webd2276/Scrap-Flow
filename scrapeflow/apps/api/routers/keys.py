"""Per-organisation API key management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from packages.core.db import get_db
from packages.core.errors import AppError, ErrorCode
from packages.core.models import ApiKey
from packages.core.scopes import Scope
from packages.core.settings import Settings
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import (
    AuthContext,
    can_grant_scopes,
    get_app_settings,
    org_rate_limit,
    require_scope,
)
from apps.api.schemas.keys import KeyCreate, KeyCreated, KeyRead
from apps.api.services import keys as key_service
from apps.api.services.audit import add_audit

router = APIRouter(prefix="/v1/keys", tags=["keys"])


def _read(key: ApiKey) -> KeyRead:
    return KeyRead(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        scopes=sorted(key.scopes),
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
    )


@router.post("", response_model=KeyCreated, status_code=201)
async def create_key(
    body: KeyCreate,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.KEYS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    _: None = Depends(org_rate_limit),
) -> KeyCreated:
    if not can_grant_scopes(context, body.scopes):
        raise AppError(
            403,
            ErrorCode.FORBIDDEN,
            "Cannot grant scopes that the calling credential does not hold",
        )
    key, plaintext = await key_service.create_key(
        db,
        org_id=context.org_id,
        name=body.name,
        scopes=body.scopes,
        created_by=context.user_id,
        pepper=settings.api_key_pepper.get_secret_value(),
        expires_at=body.expires_at,
    )
    add_audit(
        db,
        action="api_key.created",
        resource_type="api_key",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(key.id),
        details={"scopes": key.scopes},
    )
    await db.commit()
    return KeyCreated(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        key=plaintext,
        scopes=sorted(key.scopes),
        created_at=key.created_at,
        expires_at=key.expires_at,
    )


@router.get("", response_model=list[KeyRead])
async def list_keys(
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.KEYS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> list[KeyRead]:
    return [_read(key) for key in await key_service.list_keys(db, context.org_id)]


@router.delete("/{key_id}", response_model=KeyRead)
async def revoke_key(
    key_id: uuid.UUID,
    response: Response,
    context: AuthContext = Depends(require_scope(Scope.KEYS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(org_rate_limit),
) -> KeyRead:
    if context.api_key_id is not None and context.api_key_id == key_id:
        raise AppError(409, ErrorCode.CONFLICT, "Refusing to revoke the key used for this request")
    key = await key_service.revoke_key(db, org_id=context.org_id, key_id=key_id)
    add_audit(
        db,
        action="api_key.revoked",
        resource_type="api_key",
        org_id=context.org_id,
        user_id=context.user_id,
        resource_id=str(key.id),
    )
    await db.commit()
    return _read(key)
