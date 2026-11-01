"""Account lifecycle and token issuance services."""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from packages.core.errors import AppError, ErrorCode
from packages.core.models import Membership, Organization, OrgPlan, RefreshToken, Role, User
from packages.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from packages.core.settings import Settings
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


def normalise_email(email: str) -> str:
    return email.strip().lower()


# A real Argon2 hash used to equalise login timing when the email is unknown.
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def slugify_org(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:64] or "org"
    return f"{base}-{secrets.token_hex(3)}"


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime
    org_id: uuid.UUID
    user_id: uuid.UUID
    role: str


async def signup(
    db: AsyncSession,
    settings: Settings,
    *,
    org_name: str,
    email: str,
    password: str,
    display_name: str,
) -> IssuedTokens:
    if len(password) < settings.password_min_length:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"Password must be at least {settings.password_min_length} characters",
        )
    normalised = normalise_email(email)
    existing = (
        await db.execute(select(User.id).where(User.email == normalised))
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(409, ErrorCode.CONFLICT, "An account with this email already exists")

    now = datetime.now(UTC)
    org = Organization(name=org_name.strip(), slug=slugify_org(org_name), plan=OrgPlan.FREE)
    user = User(
        email=normalised,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        tos_accepted_at=now,
        tos_version=settings.tos_version,
    )
    db.add_all([org, user])
    try:
        await db.flush()
        db.add(Membership(org_id=org.id, user_id=user.id, role=Role.OWNER))
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, ErrorCode.CONFLICT, "Organization or email already exists") from exc

    return await _issue_tokens(db, settings, user=user, org=org, role=Role.OWNER)


async def login(
    db: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
    org_slug: str | None,
) -> IssuedTokens:
    user = (
        await db.execute(select(User).where(User.email == normalise_email(email)))
    ).scalar_one_or_none()
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Invalid email or password")
    if not user.is_active or not verify_password(password, user.password_hash):
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Invalid email or password")

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    query = (
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.org_id)
        .where(Membership.user_id == user.id)
        .order_by(Membership.created_at)
    )
    if org_slug:
        query = query.where(Organization.slug == org_slug)
    membership = (await db.execute(query)).first()
    if membership is None:
        raise AppError(403, ErrorCode.FORBIDDEN, "No organization membership")

    member, org = membership
    return await _issue_tokens(db, settings, user=user, org=org, role=member.role)


async def refresh(db: AsyncSession, settings: Settings, *, refresh_token: str) -> IssuedTokens:
    token_hash = hash_refresh_token(refresh_token)
    row = (
        await db.execute(
            select(RefreshToken, User, Organization)
            .join(User, User.id == RefreshToken.user_id)
            .join(Organization, Organization.id == RefreshToken.org_id)
            .where(RefreshToken.token_hash == token_hash)
        )
    ).first()
    if row is None:
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Invalid refresh token")

    stored, user, org = row
    now = datetime.now(UTC)
    if stored.revoked_at is not None:
        # Reuse of a rotated token means it leaked. Revoke the whole active
        # family so neither the attacker nor the victim keeps a usable token.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Refresh token reuse detected")
    if stored.expires_at <= now or not user.is_active:
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Refresh token expired")

    membership = (
        await db.execute(
            select(Membership).where(Membership.user_id == user.id, Membership.org_id == org.id)
        )
    ).scalar_one_or_none()
    if membership is None:
        raise AppError(403, ErrorCode.FORBIDDEN, "No organization membership")

    stored.revoked_at = now
    return await _issue_tokens(db, settings, user=user, org=org, role=membership.role)


async def logout(db: AsyncSession, refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    stored = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    ).scalar_one_or_none()
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)
        await db.commit()


async def memberships_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Organization, Role]]:
    rows = (
        await db.execute(
            select(Organization, Membership.role)
            .join(Membership, Membership.org_id == Organization.id)
            .where(Membership.user_id == user_id)
            .order_by(Membership.created_at)
        )
    ).all()
    return [(org, role) for org, role in rows]


async def _issue_tokens(
    db: AsyncSession,
    settings: Settings,
    *,
    user: User,
    org: Organization,
    role: Role,
) -> IssuedTokens:
    access, expires_in = create_access_token(
        settings, user_id=user.id, org_id=org.id, role=role.value
    )
    refresh_value = generate_refresh_token(settings)
    db.add(
        RefreshToken(
            user_id=user.id,
            org_id=org.id,
            token_hash=refresh_value.token_hash,
            expires_at=refresh_value.expires_at,
        )
    )
    await db.commit()
    return IssuedTokens(
        access_token=access,
        expires_in=expires_in,
        refresh_token=refresh_value.plaintext,
        refresh_expires_at=refresh_value.expires_at,
        org_id=org.id,
        user_id=user.id,
        role=role.value,
    )


__all__ = [
    "IssuedTokens",
    "login",
    "logout",
    "memberships_for_user",
    "normalise_email",
    "refresh",
    "signup",
    "slugify_org",
]
