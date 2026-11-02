"""Reconcile Redis quota counters with the PostgreSQL usage ledger."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from packages.core.models import (
    TERMINAL_JOB_STATUSES,
    Job,
    JobStatus,
    Organization,
    UsageLedger,
    UsageLedgerStatus,
)
from packages.core.quota import (
    PERIOD_TTL_GRACE_SECONDS,
    QuotaStore,
    ledger_usage,
    lock_org_quota,
    period_key,
    seconds_until_reset,
    settle_job_usage,
)
from packages.core.settings import Settings, get_settings
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker import job_store
from apps.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)

RECONCILE_LOCK = "sf:quota:reconcile:lock"


def _slot_ttl(settings: Settings) -> int:
    return max(settings.job_timeout_seconds + settings.job_lease_seconds, 60)


async def _active_job_ids(session: AsyncSession, org_id: uuid.UUID) -> list[uuid.UUID]:
    rows = (
        await session.execute(
            select(Job.id).where(
                Job.org_id == org_id,
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
    ).scalars()
    return list(rows)


async def _stale_ledger_rows(
    session: AsyncSession,
    *,
    limit: int,
) -> Sequence[tuple[UsageLedger, Job]]:
    rows = (
        await session.execute(
            select(UsageLedger, Job)
            .join(Job, Job.id == UsageLedger.job_id)
            .where(
                UsageLedger.status == UsageLedgerStatus.RESERVED,
                Job.status.in_(list(TERMINAL_JOB_STATUSES)),
            )
            .order_by(UsageLedger.created_at)
            .limit(limit)
        )
    ).all()
    return [(ledger, job) for ledger, job in rows]


async def _reconcile(
    *,
    settings: Settings | None = None,
    org_ids: list[uuid.UUID] | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    settings = settings or get_settings()
    current = now or datetime.now(UTC)
    period = period_key(current)
    ttl = seconds_until_reset(current) + PERIOD_TTL_GRACE_SECONDS
    maker = job_store.sessionmaker(settings)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    store = QuotaStore(redis)
    reconciled = 0
    slots = 0
    settled = 0
    try:
        async with maker() as session:
            query = select(Organization)
            if org_ids:
                query = query.where(Organization.id.in_(org_ids))
            orgs = list((await session.execute(query)).scalars())
            for org in orgs:
                await lock_org_quota(session, org.id)
                used = await ledger_usage(session, org_id=org.id, period=period)
                await store.set_usage(
                    org.id,
                    period=period,
                    used=used,
                    ttl_seconds=ttl,
                )
                active = await _active_job_ids(session, org.id)
                await store.rebuild_slots(
                    org.id,
                    job_ids=active,
                    ttl_seconds=_slot_ttl(settings),
                )
                reconciled += 1
                slots += len(active)
            await session.commit()

        async with maker() as session:
            stale = await _stale_ledger_rows(session, limit=500)
        for _ledger, job in stale:
            async with maker() as session:
                changed = await settle_job_usage(session, redis, job=job)
            if changed:
                settled += 1
    finally:
        await redis.aclose()

    logger.info(
        "quota.reconciled",
        organizations=reconciled,
        slots=slots,
        settled=settled,
        period=period,
    )
    return {"organizations": reconciled, "slots": slots, "settled": settled}


@celery_app.task(name="scrapeflow.reconcile_quotas")  # type: ignore[untyped-decorator]
def reconcile_quotas() -> dict[str, int]:
    return asyncio.run(_reconcile())
