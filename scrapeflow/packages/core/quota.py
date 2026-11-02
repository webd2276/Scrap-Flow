"""Atomic quota primitives and one-shot settlement.

Redis holds the fast counters; PostgreSQL holds the ledger that reconciliation
uses to repair Redis after a restart or a partially completed release. Job
acceptance takes a transaction-scoped advisory lock per organisation so a
reservation and a concurrent reconciliation cannot clobber each other.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.models import (
    Job,
    JobStatus,
    UsageLedger,
    UsageLedgerStatus,
)

logger = structlog.get_logger(__name__)

PERIOD_TTL_GRACE_SECONDS = 86_400

_RESERVE_LUA = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local cost = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
if used + cost > limit then
  return {0, used, limit}
end
local value = redis.call('INCRBY', KEYS[1], cost)
if redis.call('TTL', KEYS[1]) < 0 then
  redis.call('EXPIRE', KEYS[1], ttl)
end
return {1, value, limit}
"""

_RELEASE_LUA = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local cost = tonumber(ARGV[1])
local value = used - cost
if value < 0 then value = 0 end
redis.call('SET', KEYS[1], tostring(value), 'KEEPTTL')
return value
"""

_ACQUIRE_SLOT_LUA = """
local key = KEYS[1]
local job_id = ARGV[1]
local limit = tonumber(ARGV[2])
local expiry = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
local count = redis.call('ZCARD', key)
if count >= limit then
  local earliest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = 1
  if earliest[2] then
    retry = math.max(1, tonumber(earliest[2]) - now)
  end
  return {0, count, limit, math.ceil(retry)}
end
redis.call('ZADD', key, expiry, job_id)
local ttl = math.max(1000, math.ceil((expiry - now) * 1000) + 1000)
redis.call('PEXPIRE', key, ttl)
return {1, count + 1, limit, 0}
"""

_RELEASE_SLOT_LUA = """
redis.call('ZREM', KEYS[1], ARGV[1])
return redis.call('ZCARD', KEYS[1])
"""


def period_key(moment: datetime | None = None) -> str:
    current = (moment or datetime.now(UTC)).astimezone(UTC)
    return current.strftime("%Y-%m")


def next_period_start(moment: datetime | None = None) -> datetime:
    current = (moment or datetime.now(UTC)).astimezone(UTC)
    if current.month == 12:
        return datetime(current.year + 1, 1, 1, tzinfo=UTC)
    return datetime(current.year, current.month + 1, 1, tzinfo=UTC)


def seconds_until_reset(moment: datetime | None = None) -> int:
    current = (moment or datetime.now(UTC)).astimezone(UTC)
    return max(1, int((next_period_start(current) - current).total_seconds()))


@dataclass(frozen=True, slots=True)
class QuotaReservation:
    allowed: bool
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


@dataclass(frozen=True, slots=True)
class ConcurrencyLease:
    acquired: bool
    active: int
    limit: int
    retry_after: int


class QuotaStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def quota_key(org_id: uuid.UUID, period: str) -> str:
        return f"sf:quota:{org_id}:{period}"

    @staticmethod
    def concurrency_key(org_id: uuid.UUID) -> str:
        return f"sf:concurrency:{org_id}"

    async def reserve(
        self,
        org_id: uuid.UUID,
        *,
        period: str,
        cost: int,
        limit: int,
        ttl_seconds: int,
    ) -> QuotaReservation:
        raw: Any = await cast(
            Any,
            self._redis.eval(
                _RESERVE_LUA,
                1,
                self.quota_key(org_id, period),
                str(cost),
                str(limit),
                str(ttl_seconds),
            ),
        )
        allowed_raw, used_raw, limit_raw = raw
        return QuotaReservation(
            allowed=bool(int(allowed_raw)),
            used=int(used_raw),
            limit=int(limit_raw),
        )

    async def release(self, org_id: uuid.UUID, *, period: str, cost: int) -> int:
        raw: Any = await cast(
            Any,
            self._redis.eval(
                _RELEASE_LUA,
                1,
                self.quota_key(org_id, period),
                str(max(0, cost)),
            ),
        )
        return int(raw)

    async def current(self, org_id: uuid.UUID, *, period: str) -> int:
        raw: Any = await cast(
            Any,
            self._redis.get(self.quota_key(org_id, period)),
        )
        return int(raw) if raw is not None else 0

    async def set_usage(
        self,
        org_id: uuid.UUID,
        *,
        period: str,
        used: int,
        ttl_seconds: int,
    ) -> None:
        await cast(
            Any,
            self._redis.set(
                self.quota_key(org_id, period),
                str(max(0, used)),
                ex=max(1, ttl_seconds),
            ),
        )

    async def acquire_slot(
        self,
        org_id: uuid.UUID,
        *,
        job_id: uuid.UUID,
        limit: int,
        ttl_seconds: int,
    ) -> ConcurrencyLease:
        now = int(datetime.now(UTC).timestamp())
        expiry = now + max(1, ttl_seconds)
        raw: Any = await cast(
            Any,
            self._redis.eval(
                _ACQUIRE_SLOT_LUA,
                1,
                self.concurrency_key(org_id),
                str(job_id),
                str(limit),
                str(expiry),
                str(now),
            ),
        )
        acquired_raw, active_raw, limit_raw, retry_raw = raw
        return ConcurrencyLease(
            acquired=bool(int(acquired_raw)),
            active=int(active_raw),
            limit=int(limit_raw),
            retry_after=max(1, int(retry_raw)),
        )

    async def release_slot(self, org_id: uuid.UUID, *, job_id: uuid.UUID) -> int:
        raw: Any = await cast(
            Any,
            self._redis.eval(
                _RELEASE_SLOT_LUA,
                1,
                self.concurrency_key(org_id),
                str(job_id),
            ),
        )
        return int(raw)

    async def active_slots(self, org_id: uuid.UUID) -> int:
        now = int(datetime.now(UTC).timestamp())
        key = self.concurrency_key(org_id)
        await cast(Any, self._redis.zremrangebyscore(key, "-inf", now))
        raw: Any = await cast(Any, self._redis.zcard(key))
        return int(raw)

    async def rebuild_slots(
        self,
        org_id: uuid.UUID,
        *,
        job_ids: list[uuid.UUID],
        ttl_seconds: int,
    ) -> int:
        key = self.concurrency_key(org_id)
        now = int(datetime.now(UTC).timestamp())
        expiry = now + max(1, ttl_seconds)
        pipe = self._redis.pipeline(transaction=True)
        pipe.delete(key)
        for job_id in job_ids:
            pipe.zadd(key, {str(job_id): expiry})
        if job_ids:
            pipe.pexpire(key, max(1_000, ttl_seconds * 1_000))
        await cast(Any, pipe.execute())
        return len(job_ids)


async def lock_org_quota(session: AsyncSession, org_id: uuid.UUID) -> None:
    """Serialize reservation/reconciliation for one organisation."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"quota:{org_id}"},
    )


async def ledger_usage(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    period: str,
) -> int:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(UsageLedger.credits), 0)).where(
                UsageLedger.org_id == org_id,
                UsageLedger.period == period,
                UsageLedger.status.in_([UsageLedgerStatus.RESERVED, UsageLedgerStatus.COMMITTED]),
            )
        )
    ).scalar_one()
    return int(total)


def _should_commit(job: Job, started: bool | None) -> bool:
    if job.status is JobStatus.SUCCEEDED:
        return True
    executed = started if started is not None else (job.attempts > 0 or job.started_at is not None)
    return job.status in {JobStatus.FAILED, JobStatus.TIMED_OUT, JobStatus.CANCELLED} and executed


async def settle_job_usage(
    session: AsyncSession,
    redis: Redis,
    *,
    job: Job,
    started: bool | None = None,
) -> bool:
    """Settle one job's ledger row and release its concurrency slot.

    Idempotent: a second call after the ledger row left ``reserved`` returns
    ``False`` and only ensures the slot is gone. Redis failures never fail the
    job transition; reconciliation repairs the counter from PostgreSQL.
    """
    store = QuotaStore(redis)
    released_slot = False
    try:
        await store.release_slot(job.org_id, job_id=job.id)
        released_slot = True
    except Exception:
        logger.warning("quota.slot_release_failed", job_id=str(job.id), exc_info=True)

    row = (
        await session.execute(
            select(UsageLedger).where(UsageLedger.job_id == job.id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.status is not UsageLedgerStatus.RESERVED:
        if not released_slot:
            logger.warning("quota.settle_skipped", job_id=str(job.id))
        return False

    commit = _should_commit(job, started)
    if commit:
        row.status = UsageLedgerStatus.COMMITTED
        row.reason = "job_succeeded" if job.status is JobStatus.SUCCEEDED else "job_started"
    else:
        row.status = UsageLedgerStatus.RELEASED
        row.reason = "job_never_started"
        try:
            await store.release(job.org_id, period=row.period, cost=row.credits)
        except Exception:
            logger.warning("quota.release_failed", job_id=str(job.id), exc_info=True)
    row.settled_at = datetime.now(UTC)
    await session.commit()
    return True
