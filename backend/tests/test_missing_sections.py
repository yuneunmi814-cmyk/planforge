"""ProjectRes.missingSections flags partial documents from weak local models."""

from app.core import database
from app.models import SECTION_TYPES, Section
from app.services.queue import get_queue
from app.worker.processor import process_job
from tests.conftest import auth_headers


def _drain():
    q = get_queue()
    while True:
        p = q.dequeue(timeout=0)
        if not p:
            break
        with database.SessionLocal() as db:
            process_job(db, p["jobId"])


def test_full_generation_reports_nothing_missing(client):
    headers = auth_headers(client)
    pid = client.post("/api/v1/projects", json={"idea": "헬스장 SaaS"}, headers=headers).json()["projectId"]
    _drain()  # FakeLLM emits all 9 sections
    body = client.get(f"/api/v1/projects/{pid}", headers=headers).json()
    assert body["missingSections"] == []


def test_partial_document_lists_missing(client, db_session):
    headers = auth_headers(client)
    pid = client.post("/api/v1/projects", json={"idea": "x"}, headers=headers).json()["projectId"]
    # Simulate a weak model that produced only one section (do not drain).
    db_session.add(Section(project_id=pid, type="overview", title="overview", markdown="m", version=1, is_latest=True))
    db_session.commit()

    body = client.get(f"/api/v1/projects/{pid}", headers=headers).json()
    assert "overview" not in body["missingSections"]
    assert "api_spec" in body["missingSections"]
    assert len(body["missingSections"]) == len(SECTION_TYPES) - 1


def test_empty_project_reports_no_missing(client):
    headers = auth_headers(client)
    pid = client.post("/api/v1/projects", json={"idea": "x"}, headers=headers).json()["projectId"]
    # No sections yet → not "missing", just not generated.
    body = client.get(f"/api/v1/projects/{pid}", headers=headers).json()
    assert body["missingSections"] == []
