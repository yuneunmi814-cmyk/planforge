"""The desktop webview is a cross-origin caller (tauri://localhost on macOS,
http://tauri.localhost on Windows, http://localhost:3000 in dev). Without a CORS
allowance for those origins every fetch from the app to the sidecar fails, so the
whole desktop app is dead on arrival. These tests lock in the allowance."""

import pytest


@pytest.mark.parametrize(
    "origin",
    ["tauri://localhost", "http://tauri.localhost", "http://localhost:3000", "http://127.0.0.1:8000"],
)
def test_cors_preflight_allows_local_and_tauri_origins(client, origin):
    res = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == origin


def test_cors_rejects_foreign_origin(client):
    res = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    # A non-allowed origin gets no echoing ACAO header → the browser blocks it.
    assert res.headers.get("access-control-allow-origin") != "https://evil.example.com"
