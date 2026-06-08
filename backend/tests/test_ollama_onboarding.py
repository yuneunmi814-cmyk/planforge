"""Ollama install/onboarding endpoints: status, open-download, pull guard."""

import webbrowser

from tests.conftest import auth_headers


def test_status_shape(client):
    headers = auth_headers(client)
    res = client.get("/api/v1/settings/ollama/status", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert set(["installed", "running", "models", "downloadUrl"]) <= body.keys()
    assert isinstance(body["installed"], bool)
    assert isinstance(body["running"], bool)
    assert body["downloadUrl"].startswith("https://")


def test_open_download_invokes_browser(client, monkeypatch):
    headers = auth_headers(client)
    calls = []
    monkeypatch.setattr(webbrowser, "open", lambda url: calls.append(url) or True)
    res = client.post("/api/v1/settings/ollama/open-download", headers=headers)
    assert res.status_code == 200
    assert res.json()["opened"] is True
    assert calls and calls[0].startswith("https://ollama.com")


def test_pull_requires_running_ollama(client):
    headers = auth_headers(client)
    # Point at a dead port so Ollama is definitely "not running".
    client.put("/api/v1/settings", json={"ollamaBaseUrl": "http://localhost:1"}, headers=headers)
    res = client.post("/api/v1/settings/ollama/pull", json={"model": "llama3.1"}, headers=headers)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONFLICT"


def test_onboarding_requires_auth(client):
    assert client.get("/api/v1/settings/ollama/status").status_code == 401
