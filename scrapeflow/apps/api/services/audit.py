"""Write audit records. Callers own the transaction."""

from __future__ import annotations

import uuid
from typing import Any

from packages.core.models import AuditLog
from sqlalchemy.ext.asyncio import AsyncSession


def add_audit(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    org_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    resource_id: str | None = None,
    ip_hash: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            org_id=org_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_hash=ip_hash,
            details=details or {},
        )
    )
