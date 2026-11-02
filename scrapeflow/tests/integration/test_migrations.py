from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

ROOT = Path(__file__).resolve().parents[2]


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def test_alembic_upgrade_creates_schema_and_matches_models(
    database_url: str, redis_url: str
) -> None:
    dsn = _dsn(database_url)
    parts = urlsplit(dsn)
    database_name = f"sf_mig_{uuid.uuid4().hex[:8]}"
    admin_dsn = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    new_dsn = urlunsplit((parts.scheme, parts.netloc, f"/{database_name}", parts.query, ""))

    async def create_database() -> None:
        connection = await asyncpg.connect(admin_dsn)
        try:
            await connection.execute(f'CREATE DATABASE "{database_name}"')
        finally:
            await connection.close()

    async def drop_database() -> None:
        connection = await asyncpg.connect(admin_dsn)
        try:
            await connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                database_name,
            )
            await connection.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        finally:
            await connection.close()

    async def tables() -> set[str]:
        connection = await asyncpg.connect(new_dsn)
        try:
            rows = await connection.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            return {row["table_name"] for row in rows}
        finally:
            await connection.close()

    import asyncio

    asyncio.run(create_database())
    try:
        env = {
            **os.environ,
            "DATABASE_URL": new_dsn,
            "REDIS_URL": redis_url,
            "API_KEY_PEPPER": "a" * 40,
            "JWT_SECRET": "b" * 40,
            "WEBHOOK_SECRET_KEY": "c" * 40,
        }

        def alembic(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(  # noqa: S603 - fixed, trusted argv
                [sys.executable, "-m", "alembic", *args],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )

        upgrade = alembic("upgrade", "head")
        assert upgrade.returncode == 0, upgrade.stderr

        check = alembic("check")
        assert check.returncode == 0, check.stdout + check.stderr

        expected = {
            "alembic_version",
            "organizations",
            "users",
            "memberships",
            "api_keys",
            "refresh_tokens",
            "audit_logs",
            "jobs",
            "job_events",
            "artifacts",
            "usage_ledger",
            "stripe_events",
        }
        assert expected <= asyncio.run(tables())

        # Downgrade is verified only on this disposable database.
        downgrade = alembic("downgrade", "base")
        assert downgrade.returncode == 0, downgrade.stderr
        after_downgrade = asyncio.run(tables())
        assert not (expected - {"alembic_version"}) & after_downgrade

        reupgrade = alembic("upgrade", "head")
        assert reupgrade.returncode == 0, reupgrade.stderr
        assert expected <= asyncio.run(tables())
    finally:
        asyncio.run(drop_database())
