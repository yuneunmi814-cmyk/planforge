"""Fixed-window rate limiter (design §api_spec: 레이트 리밋 → 429).

Swappable behind an interface so tests use an in-memory limiter:
- RedisRateLimiter: shared across processes via INCR + EXPIRE.
- InMemoryRateLimiter: per-process, time-based window (test/dev).

hit() returns (allowed, retry_after_seconds). retry_after is 0 when allowed."""

from __future__ import annotations

import time
from typing import Protocol

from app.core.config import get_settings

settings = get_settings()


class RateLimiter(Protocol):
    def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]: ...


class RedisRateLimiter:
    def __init__(self) -> None:
        import redis

        self._redis = redis.from_url(settings.redis_url, decode_responses=True)

    def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        full_key = f"planforge:ratelimit:{key}"
        count = self._redis.incr(full_key)
        if count == 1:
            self._redis.expire(full_key, window)
        if count <= limit:
            return True, 0
        ttl = self._redis.ttl(full_key)
        return False, max(int(ttl), 1)


class InMemoryRateLimiter:
    """Per-process fixed window keyed on the current wall-clock window index."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[int, float]] = {}  # key → (count, reset_at)

    def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        now = time.time()
        count, reset_at = self._buckets.get(key, (0, now + window))
        if now >= reset_at:
            count, reset_at = 0, now + window
        count += 1
        self._buckets[key] = (count, reset_at)
        if count <= limit:
            return True, 0
        return False, max(int(reset_at - now), 1)


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RedisRateLimiter()
    return _limiter


def set_rate_limiter(limiter: RateLimiter | None) -> None:
    """Override the active limiter (used by tests)."""
    global _limiter
    _limiter = limiter
