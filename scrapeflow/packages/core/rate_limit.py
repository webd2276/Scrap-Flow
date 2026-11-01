"""Atomic Redis token-bucket rate limiting."""

from __future__ import annotations

import math
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, cast

from redis.asyncio import Redis

# KEYS[1] bucket, ARGV: capacity, refill_per_second, cost
_TOKEN_BUCKET_LUA = """
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) + tonumber(now_parts[2]) / 1000000

local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil or ts == nil then
  tokens = capacity
  ts = now
end

local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', tostring(now))
local ttl_ms = math.ceil((capacity / refill) * 1000) + 5000
redis.call('PEXPIRE', KEYS[1], ttl_ms)

local wait = 0
if allowed == 0 then
  wait = math.ceil((cost - tokens) / refill)
end
local reset = math.ceil((capacity - tokens) / refill)
return {allowed, math.floor(tokens), wait, reset}
"""


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_after: int

    def headers(self) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset_after),
        }
        if not self.allowed:
            headers["Retry-After"] = str(self.retry_after)
        return headers


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def consume(
        self,
        key: str,
        *,
        capacity: int,
        refill_per_second: float,
        cost: int = 1,
    ) -> RateLimitResult:
        if capacity < 1 or refill_per_second <= 0 or cost < 1:
            raise ValueError("Invalid token bucket configuration")

        raw: Any = await cast(
            Awaitable[Any],
            self._redis.eval(
                _TOKEN_BUCKET_LUA,
                1,
                key,
                str(capacity),
                str(refill_per_second),
                str(cost),
            ),
        )
        allowed_raw, remaining_raw, wait_raw, reset_raw = raw
        remaining = max(0, min(capacity, int(remaining_raw)))
        return RateLimitResult(
            allowed=bool(int(allowed_raw)),
            limit=capacity,
            remaining=remaining,
            retry_after=max(0, math.ceil(float(wait_raw))),
            reset_after=max(0, math.ceil(float(reset_raw))),
        )
