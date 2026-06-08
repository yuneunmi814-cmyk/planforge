"""Test fixtures: isolated in-memory SQLite, in-memory queue, fake LLM.

No Redis, no network, no API key required — the whole pipeline runs in-process.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import database, ratelimit
from app.core.database import Base, get_db
from app.core.ratelimit import InMemoryRateLimiter
from app.main import app
from app.services import appconfig, events, llm, queue
from app.services.events import InMemoryEventBus
from app.services.llm import FakeLLMClient
from app.services.queue import InMemoryQueue


@pytest.fixture()
def db_session():
    # Shared in-memory DB across connections within one test.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    # Point the app's SessionLocal at the test engine (worker/inline paths use it).
    database.SessionLocal = TestingSessionLocal
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    # Isolate the runtime settings store to a temp dir (never touch ~/.planforge).
    tmp_data = tempfile.mkdtemp(prefix="planforge-test-")
    prev_data_dir = os.environ.get("PLANFORGE_DATA_DIR")
    os.environ["PLANFORGE_DATA_DIR"] = tmp_data
    appconfig.reset()

    app.dependency_overrides[get_db] = _override_get_db
    queue.set_queue(InMemoryQueue())
    llm.set_llm(FakeLLMClient())
    events.set_event_bus(InMemoryEventBus())
    ratelimit.set_rate_limiter(InMemoryRateLimiter())
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    queue.set_queue(None)
    llm.set_llm(None)
    events.set_event_bus(None)
    ratelimit.set_rate_limiter(None)
    appconfig.reset()
    if prev_data_dir is None:
        os.environ.pop("PLANFORGE_DATA_DIR", None)
    else:
        os.environ["PLANFORGE_DATA_DIR"] = prev_data_dir


def auth_headers(client: TestClient, email="admin@example.com", password="password123"):
    """Sign up (first user → approved admin) and return Bearer auth headers."""
    client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = res.json()["accessToken"]
    return {"Authorization": f"Bearer {token}"}
