"""PF-0: every error leaves the API as {"error":{"code","message"}}."""


def _assert_envelope(res, code: str):
    assert res.json().keys() == {"error"}
    body = res.json()["error"]
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]


def test_unauthorized_envelope(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401
    _assert_envelope(res, "UNAUTHORIZED")


def test_not_found_envelope(client):
    from tests.conftest import auth_headers

    headers = auth_headers(client)
    res = client.get("/api/v1/projects/999999", headers=headers)
    assert res.status_code == 404
    _assert_envelope(res, "NOT_FOUND")


def test_conflict_envelope(client):
    client.post("/api/v1/auth/signup", json={"email": "a@b.com", "password": "password123"})
    res = client.post("/api/v1/auth/signup", json={"email": "a@b.com", "password": "password123"})
    assert res.status_code == 409
    _assert_envelope(res, "CONFLICT")


def test_validation_envelope(client):
    res = client.post("/api/v1/auth/signup", json={"email": "not-an-email", "password": "short"})
    assert res.status_code == 422
    _assert_envelope(res, "VALIDATION_ERROR")
