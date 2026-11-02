"""Purge expired artifacts from storage and PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from packages.core.artifacts import ArtifactStore, ArtifactStoreError
from packages.core.models import Artifact
from packages.core.settings import Settings, get_settings
from sqlalchemy import delete, select

from apps.worker import job_store
from apps.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _purge(
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    settings = settings or get_settings()
    current = now or datetime.now(UTC)
    batch = limit or settings.artifact_retention_batch_size
    store = ArtifactStore(settings)
    maker = job_store.sessionmaker(settings)
    deleted = 0
    failed = 0

    async with maker() as session:
        rows = list(
            (
                await session.execute(
                    select(Artifact)
                    .where(
                        Artifact.expires_at.is_not(None),
                        Artifact.expires_at <= current,
                    )
                    .order_by(Artifact.expires_at)
                    .limit(batch)
                )
            ).scalars()
        )

    for artifact in rows:
        try:
            await asyncio.to_thread(store.delete, artifact.storage_key)
        except ArtifactStoreError:
            failed += 1
            logger.warning(
                "artifacts.delete_failed",
                artifact_id=str(artifact.id),
                storage_key=artifact.storage_key,
            )
            continue
        async with maker() as session:
            await session.execute(delete(Artifact).where(Artifact.id == artifact.id))
            await session.commit()
        deleted += 1

    logger.info("artifacts.purged", deleted=deleted, failed=failed)
    return {"deleted": deleted, "failed": failed}


@celery_app.task(name="scrapeflow.purge_artifacts")  # type: ignore[untyped-decorator]
def purge_artifacts() -> dict[str, int]:
    return asyncio.run(_purge())
