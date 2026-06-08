from tests.conftest import auth_headers


def test_signup_first_user_is_admin_then_login_refresh(client):
    res = client.post(
        "/api/v1/auth/signup", json={"email": "a@b.com", "password": "password123"}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["role"] == "admin"
    assert body["status"] == "approved"

    res = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "password123"})
    assert res.status_code == 200
    tokens = res.json()
    assert tokens["accessToken"] and tokens["refreshToken"]

    res = client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert res.status_code == 200
    assert res.json()["accessToken"]


def test_duplicate_signup_conflicts(client):
    client.post("/api/v1/auth/signup", json={"email": "a@b.com", "password": "password123"})
    res = client.post("/api/v1/auth/signup", json={"email": "a@b.com", "password": "password123"})
    assert res.status_code == 409


def test_wrong_password_rejected(client):
    client.post("/api/v1/auth/signup", json={"email": "a@b.com", "password": "password123"})
    res = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "wrongpass1"})
    assert res.status_code == 401


def test_second_user_is_pending_and_blocked_from_generation(client):
    auth_headers(client)  # first user = admin
    client.post("/api/v1/auth/signup", json={"email": "u2@b.com", "password": "password123"})
    res = client.post("/api/v1/auth/login", json={"email": "u2@b.com", "password": "password123"})
    assert res.json()["status"] == "pending"
    headers = {"Authorization": f"Bearer {res.json()['accessToken']}"}
    res = client.post("/api/v1/projects", json={"idea": "x"}, headers=headers)
    assert res.status_code == 403


def test_me_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
