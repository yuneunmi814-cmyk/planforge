"""Job queue (Redis). Real redis-py adapter behind a swappable interface so
tests can use an in-memory queue."""

from __future__ import annotations

import json
from collections import deque
from typing import Protocol

from app.core.config import get_settings

settings = get_settings()


class JobQueue(Protocol):
    def enqueue(self, payload: dict) -> None: ...
    def dequeue(self, timeout: int = 5) -> dict | None: ...
    def size(self) -> int: ...


class RedisQueue:
    """Real Redis list-backed queue (RPUSH / BLPOP)."""

    def __init__(self) -> None:
        import redis

        self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        self._name = settings.job_queue_name

    def enqueue(self, payload: dict) -> None:
        self._redis.rpush(self._name, json.dumps(payload))

    def dequeue(self, timeout: int = 5) -> dict | None:
        item = self._redis.blpop(self._name, timeout=timeout)
        if item is None:
            return None
        _key, value = item
        return json.loads(value)

    def size(self) -> int:
        return int(self._redis.llen(self._name))


class InMemoryQueue:
    """Test/dev fallback. Not durable, single-process."""

    def __init__(self) -> None:
        self._items: deque[dict] = deque()

    def enqueue(self, payload: dict) -> None:
        self._items.append(payload)

    def dequeue(self, timeout: int = 5) -> dict | None:
        return self._items.popleft() if self._items else None

    def size(self) -> int:
        return len(self._items)


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = RedisQueue()
    return _queue


def set_queue(queue: JobQueue | None) -> None:
    """Override the active queue (used by tests)."""
    global _queue
    _queue = queue
