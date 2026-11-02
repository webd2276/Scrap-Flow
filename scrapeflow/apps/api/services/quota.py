"""API-facing quota reservation, headers, and plan limit errors."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from packages.core.errors import AppError, ErrorCode
from packages.core.models import UsageLedger, UsageLedgerStatus
from packages.core.plans import Plan
from packages.core.quota import (
    PERIOD_TTL_GRACE_SECONDS,
    ConcurrencyLease,
    QuotaReservation,
    QuotaStore,
    ledger_usage,
    lock_org_quota,
    period_key,
    seconds_until_reset,
)
from packages.core.settings import Settings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class QuotaState:
    plan: Plan
    period: str
    reservation: QuotaReservation
    lease: ConcurrencyLease
    reset_seconds: int

    def headers(self) -> dict[str, str]:
        return {
            "X-Quota-Limit": str(self.reservation.limit),
            "X-Quota-Remaining": str(self.reservation.remaining),
            "X-Quota-Reset": str(self.reset_seconds),
            "X-Concurrency-Limit": str(self.lease.limit),
            "X-Concurrency-Remaining": str(max(0, self.lease.limit - self.lease.active)),
        }


def concurrency_ttl(settings: Settings) -> int:
    return max(settings.job_timeout_seconds + settings.job_lease_seconds, 60)


def reservation_ttl() -> int:
    return seconds_until_reset() + PERIOD_TTL_GRACE_SECONDS


def _quota_headers(plan: Plan, used: int, reset_seconds: int) -> dict[str, str]:
    return {
        "X-Quota-Limit": str(plan.monthly_credits),
        "X-Quota-Remaining": str(max(0, plan.monthly_credits - used)),
        "X-Quota-Reset": str(reset_seconds),
    }


async def current_used(
    db: AsyncSession,
    redis: Redis,
    *,
    org_id: uuid.UUID,
    period: str | None = None,
) -> int:
    """Return the authoritative used count, repairing a cold Redis counter."""
    selected = period or period_key()
    store = QuotaStore(redis)
    used = await store.current(org_id, period=selected)
    recorded = await ledger_usage(db, org_id=org_id, period=selected)
    if recorded <= used:
        return used
    await lock_org_quota(db, org_id)
    used = await store.current(org_id, period=selected)
    recorded = await ledger_usage(db, org_id=org_id, period=selected)
    if recorded > used:
        await store.set_usage(
            org_id,
            period=selected,
            used=recorded,
            ttl_seconds=reservation_ttl(),
        )
        return recorded
    return used


async def reserve_job(
    db: AsyncSession,
    redis: Redis,
    *,
    settings: Settings,
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    plan: Plan,
    cost: int,
) -> QuotaState:
    """Acquire a concurrency slot and reserve credits atomically.

    The caller owns the surrounding transaction. On any later failure it must
    call :func:`release_reservation` after rolling back.
    """
    await lock_org_quota(db, org_id)
    store = QuotaStore(redis)
    lease = await store.acquire_slot(
        org_id,
        job_id=job_id,
        limit=plan.max_concurrency,
        ttl_seconds=concurrency_ttl(settings),
    )
    reset = seconds_until_reset()
    if not lease.acquired:
        headers = {
            "X-Concurrency-Limit": str(lease.limit),
            "X-Concurrency-Remaining": "0",
            "Retry-After": str(lease.retry_after),
        }
        raise AppError(
            429,
            ErrorCode.CONCURRENCY_LIMIT,
            f"Your {plan.name} plan allows {plan.max_concurrency} concurrent job(s)",
            headers=headers,
        )

    period = period_key()
    reservation = await store.reserve(
        org_id,
        period=period,
        cost=cost,
        limit=plan.monthly_credits,
        ttl_seconds=reservation_ttl(),
    )
    if not reservation.allowed:
        await store.release_slot(org_id, job_id=job_id)
        headers = _quota_headers(plan, reservation.used, reset)
        headers["Retry-After"] = str(reset)
        raise AppError(
            402,
            ErrorCode.QUOTA_EXCEEDED,
            f"Monthly quota exceeded for the {plan.name} plan",
            headers=headers,
        )

    return QuotaState(
        plan=plan,
        period=period,
        reservation=reservation,
        lease=lease,
        reset_seconds=reset,
    )


def add_ledger_entry(
    db: AsyncSession,
    *,
    state: QuotaState,
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    credits: int,
) -> UsageLedger:
    row = UsageLedger(
        org_id=org_id,
        job_id=job_id,
        period=state.period,
        credits=credits,
        status=UsageLedgerStatus.RESERVED,
        reason="job",
    )
    db.add(row)
    return row


async def release_reservation(
    redis: Redis,
    *,
    state: QuotaState,
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    credits: int,
) -> None:
    store = QuotaStore(redis)
    try:
        await store.release(org_id, period=state.period, cost=credits)
    finally:
        await store.release_slot(org_id, job_id=job_id)


async def replay_state(
    db: AsyncSession,
    redis: Redis,
    *,
    org_id: uuid.UUID,
    plan: Plan,
) -> QuotaState:
    used = await current_used(db, redis, org_id=org_id)
    active = await QuotaStore(redis).active_slots(org_id)
    reset = seconds_until_reset()
    return QuotaState(
        plan=plan,
        period=period_key(),
        reservation=QuotaReservation(
            allowed=True,
            used=used,
            limit=plan.monthly_credits,
        ),
        lease=ConcurrencyLease(
            acquired=True,
            active=active,
            limit=plan.max_concurrency,
            retry_after=0,
        ),
        reset_seconds=reset,
    )


async def usage_summary(
    db: AsyncSession,
    redis: Redis,
    *,
    org_id: uuid.UUID,
    plan: Plan,
) -> dict[str, int | str]:
    used = await current_used(db, redis, org_id=org_id)
    return {
        "plan": plan.code.value,
        "plan_name": plan.name,
        "monthly_credits": plan.monthly_credits,
        "used": used,
        "remaining": max(0, plan.monthly_credits - used),
        "reset_seconds": seconds_until_reset(),
        "max_concurrency": plan.max_concurrency,
        "max_steps": plan.max_steps,
        "max_pages": plan.max_pages,
        "artifact_retention_days": plan.artifact_retention_days,
        "period": period_key(),
    }


async def raise_plan_limit(
    db: AsyncSession,
    redis: Redis,
    *,
    org_id: uuid.UUID,
    plan: Plan,
    message: str,
) -> None:
    used = await current_used(db, redis, org_id=org_id)
    reset = seconds_until_reset()
    headers = _quota_headers(plan, used, reset)
    headers["Retry-After"] = str(reset)
    raise AppError(402, ErrorCode.QUOTA_EXCEEDED, message, headers=headers)


def artifact_expiry(plan: Plan, now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    return current + timedelta(days=plan.artifact_retention_days)
