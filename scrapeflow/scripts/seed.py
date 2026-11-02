"""Seed a local demo organisation and API key.

Idempotent: re-running creates a fresh key for the demo org and prints it once.
"""

from __future__ import annotations

import asyncio
import secrets

from apps.api.services.keys import create_key
from packages.core.db import create_engine, create_sessionmaker
from packages.core.models import Membership, Organization, OrgPlan, Role, User
from packages.core.scopes import Scope
from packages.core.security import hash_password
from packages.core.settings import get_settings
from sqlalchemy import select

DEMO_SLUG = "demo"
DEMO_EMAIL = "demo@example.com"


async def seed() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)

    async with sessionmaker() as db:
        org = (
            await db.execute(select(Organization).where(Organization.slug == DEMO_SLUG))
        ).scalar_one_or_none()
        user = (await db.execute(select(User).where(User.email == DEMO_EMAIL))).scalar_one_or_none()

        generated_password: str | None = None
        if org is None:
            org = Organization(name="Demo Organisation", slug=DEMO_SLUG, plan=OrgPlan.FREE)
            db.add(org)
            await db.flush()

        if user is None:
            generated_password = secrets.token_urlsafe(18)
            user = User(
                email=DEMO_EMAIL,
                password_hash=hash_password(generated_password),
                display_name="Demo Owner",
                tos_version=settings.tos_version,
            )
            db.add(user)
            await db.flush()

        membership = (
            await db.execute(
                select(Membership).where(Membership.org_id == org.id, Membership.user_id == user.id)
            )
        ).scalar_one_or_none()
        if membership is None:
            db.add(Membership(org_id=org.id, user_id=user.id, role=Role.OWNER))
        await db.commit()

        key, plaintext = await create_key(
            db,
            org_id=org.id,
            name="seeded demo key",
            scopes=[Scope.ADMIN.value],
            created_by=user.id,
            pepper=settings.api_key_pepper.get_secret_value(),
            expires_at=None,
        )

    await engine.dispose()

    print("ScrapeFlow demo seed")
    print(f"  org:      {org.name} ({org.slug})")
    print(f"  plan:     {org.plan.value}")
    print(f"  email:    {user.email}")
    if generated_password:
        print(f"  password: {generated_password}")
    else:
        print("  password: (unchanged; set DEMO_PASSWORD on first seed if you need it)")
    print(f"  key id:   {key.id}")
    print(f"  api key:  {plaintext}   # shown once")


if __name__ == "__main__":
    asyncio.run(seed())
