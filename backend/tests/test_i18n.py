"""Backend error messages localize via Accept-Language; default is English."""


def test_default_is_english(client):
    res = client.post("/api/v1/auth/login", json={"email": "x@y.com", "password": "nope12345"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"
    assert res.json()["error"]["message"] == "Incorrect email or password."


def test_korean_via_accept_language(client):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "x@y.com", "password": "nope12345"},
        headers={"Accept-Language": "ko"},
    )
    assert res.json()["error"]["message"] == "이메일 또는 비밀번호가 올바르지 않습니다."


def test_unknown_key_passes_through(client):
    # A dynamic/non-catalog message (e.g. an LLM reason) is returned verbatim.
    from app.core import i18n

    assert i18n.translate("some dynamic reason", "ko") == "some dynamic reason"
    assert i18n.translate("rate_limited", "en") == "Too many requests. Please try again shortly."
