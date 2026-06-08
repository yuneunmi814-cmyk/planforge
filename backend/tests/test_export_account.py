"""PF-5: document export (md/json) + account withdrawal/retention policy."""

from app.core import database
from app.models import SECTION_TYPES, AuditLog, Project, Section, UsageLog, User
from app.services.queue import get_queue
from app.worker.processor import process_job
from tests.conftest import auth_headers


def _drain_queue():
    q = get_queue()
    while True:
        payload = q.dequeue(timeout=0)
        if not payload:
            break
        with database.SessionLocal() as db:
            process_job(db, payload["jobId"])


def _make_project(client, headers):
    res = client.post("/api/v1/projects", json={"idea": "동네 헬스장 SaaS"}, headers=headers)
    pid = res.json()["projectId"]
    _drain_queue()
    return pid


def test_export_markdown(client):
    headers = auth_headers(client)
    pid = _make_project(client, headers)
    res = client.get(f"/api/v1/projects/{pid}/export?format=md", headers=headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/markdown")
    assert "attachment" in res.headers["content-disposition"]
    # All 9 section titles present, in spec order.
    body = res.text
    positions = [body.find(t) for t in SECTION_TYPES]
    assert all(p != -1 for p in positions)
    assert positions == sorted(positions)


def test_export_json(client):
    headers = auth_headers(client)
    pid = _make_project(client, headers)
    res = client.get(f"/api/v1/projects/{pid}/export?format=json", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert [s["type"] for s in body["sections"]] == list(SECTION_TYPES)
    assert body["assumedStack"]["backend"]


def test_export_bad_format_422(client):
    headers = auth_headers(client)
    pid = _make_project(client, headers)
    assert client.get(f"/api/v1/projects/{pid}/export?format=pdf", headers=headers).status_code == 422


def test_delete_account_purges_pii_and_retains_logs(client, db_session):
    headers = auth_headers(client)
    pid = _make_project(client, headers)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    uid = me["id"]

    res = client.delete("/api/v1/account", headers=headers)
    assert res.status_code == 200
    summary = res.json()
    assert any("account_pii" in p for p in summary["purged"])
    assert any("usage_logs" in r for r in summary["retained"])

    # PII purged: email anonymised, password destroyed, status disabled.
    user = db_session.get(User, uid)
    assert user.email == f"deleted-user-{uid}@deleted.invalid"
    assert user.password_hash == ""
    assert user.status == "disabled"

    # Project content soft-deleted.
    project = db_session.get(Project, pid)
    assert project.deleted_at is not None
    # Sections still rows but project hidden from API.
    assert client.get(f"/api/v1/projects/{pid}", headers=headers).status_code in (403, 404)

    # Retained (pseudonymised) trails still reference the user_id.
    assert db_session.query(UsageLog).filter_by(user_id=uid).count() >= 1
    assert db_session.query(AuditLog).filter_by(actor_user_id=uid, action="account.delete").count() == 1


def test_deleted_user_cannot_login(client):
    headers = auth_headers(client)
    _make_project(client, headers)
    client.delete("/api/v1/account", headers=headers)
    # Email anonymised + password destroyed → original credentials fail.
    res = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "password123"}
    )
    assert res.status_code == 401
