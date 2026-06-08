"""Regression: in local/desktop mode (inline_dispatch) there is no Redis, so the
rate limiter and event bus must fall back to in-memory implementations.

This caught a real bug: the bundled app 500'd on every generation because the
rate limiter hardcoded Redis."""

from app.core import ratelimit
from app.core.config import get_settings
from app.core.ratelimit import InMemoryRateLimiter, RedisRateLimiter, get_rate_limiter
from app.services import events
from app.services.events import InMemoryEventBus, RedisEventBus, get_event_bus


def test_inline_mode_uses_inmemory(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "inline_dispatch", True)
    ratelimit.set_rate_limiter(None)
    events.set_event_bus(None)
    assert isinstance(get_rate_limiter(), InMemoryRateLimiter)
    assert isinstance(get_event_bus(), InMemoryEventBus)
    ratelimit.set_rate_limiter(None)
    events.set_event_bus(None)


def test_server_mode_uses_redis(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "inline_dispatch", False)
    ratelimit.set_rate_limiter(None)
    events.set_event_bus(None)
    # Construction is lazy (no connection yet), so this is safe without Redis.
    assert isinstance(get_rate_limiter(), RedisRateLimiter)
    assert isinstance(get_event_bus(), RedisEventBus)
    ratelimit.set_rate_limiter(None)
    events.set_event_bus(None)
