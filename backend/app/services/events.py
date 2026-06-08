"""Per-job progress events (design §user_flow: 진행률 / 점진 노출).

History-backed so it works uniformly for SSE polling and is synchronously
testable: the worker appends events as it progresses; the SSE endpoint replays
the history and tails new events until a terminal event arrives.

- InMemoryEventBus: dict of job_id → event list (test/dev, single process).
- RedisEventBus: a capped, expiring list per job (RPUSH/LRANGE) so multiple API
  processes and the worker share the same stream.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Protocol

from app.core.config import get_settings

settings = get_settings()

# Events whose arrival means the stream can close.
TERMINAL_EVENTS = ("success", "rejected", "failed")


class EventBus(Protocol):
    def publish(self, job_id: int, event: dict) -> None: ...
    def history(self, job_id: int) -> list[dict]: ...


class InMemoryEventBus:
    def __init__(self) -> None:
        self._events: dict[int, list[dict]] = defaultdict(list)

    def publish(self, job_id: int, event: dict) -> None:
        self._events[job_id].append(event)

    def history(self, job_id: int) -> list[dict]:
        return list(self._events[job_id])


class RedisEventBus:
    def __init__(self) -> None:
        import redis

        self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        self._ttl = settings.job_event_ttl_seconds

    def _key(self, job_id: int) -> str:
        return f"{settings.job_event_key_prefix}{job_id}"

    def publish(self, job_id: int, event: dict) -> None:
        key = self._key(job_id)
        pipe = self._redis.pipeline()
        pipe.rpush(key, json.dumps(event, ensure_ascii=False))
        pipe.expire(key, self._ttl)
        pipe.execute()

    def history(self, job_id: int) -> list[dict]:
        return [json.loads(v) for v in self._redis.lrange(self._key(job_id), 0, -1)]


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = RedisEventBus()
    return _bus


def set_event_bus(bus: EventBus | None) -> None:
    """Override the active bus (used by tests)."""
    global _bus
    _bus = bus
