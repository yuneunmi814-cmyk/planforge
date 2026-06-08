"""Runtime LLM settings: defaults, key masking, provider switch, engine build."""

import pytest

from app.services import appconfig, llm
from app.services.llm import AnthropicClient, FakeLLMClient, OllamaClient
from tests.conftest import auth_headers


def test_get_settings_defaults(client):
    headers = auth_headers(client)
    res = client.get("/api/v1/settings", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["llmProvider"] in ("ollama", "anthropic", "fake")
    assert body["ollamaBaseUrl"].startswith("http")
    assert body["hasAnthropicKey"] is False
    assert body["anthropicKeyMasked"] == ""


def test_set_anthropic_key_is_masked(client):
    headers = auth_headers(client)
    res = client.put(
        "/api/v1/settings",
        json={"llmProvider": "anthropic", "anthropicApiKey": "sk-secret-12345678"},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["llmProvider"] == "anthropic"
    assert body["hasAnthropicKey"] is True
    assert body["anthropicKeyMasked"] == "••••5678"
    assert "secret" not in body["anthropicKeyMasked"]


def test_switch_to_ollama_model(client):
    headers = auth_headers(client)
    res = client.put(
        "/api/v1/settings",
        json={"llmProvider": "ollama", "ollamaModel": "qwen2.5"},
        headers=headers,
    )
    assert res.json()["ollamaModel"] == "qwen2.5"


def test_invalid_provider_422(client):
    headers = auth_headers(client)
    res = client.put("/api/v1/settings", json={"llmProvider": "gpt5"}, headers=headers)
    assert res.status_code == 422


def test_settings_requires_auth(client):
    assert client.get("/api/v1/settings").status_code == 401


def test_engine_build_from_config(client):
    """_build_from_config picks the right client per stored settings."""
    headers = auth_headers(client)

    client.put("/api/v1/settings", json={"llmProvider": "ollama"}, headers=headers)
    llm.set_llm(None)
    assert isinstance(llm._build_from_config(), OllamaClient)

    client.put(
        "/api/v1/settings",
        json={"llmProvider": "anthropic", "anthropicApiKey": "sk-abc-1234"},
        headers=headers,
    )
    pytest.importorskip("anthropic")  # the SDK is bundled in the real app
    assert isinstance(llm._build_from_config(), AnthropicClient)

    # Anthropic selected but no key → safe fallback to the stub.
    client.put("/api/v1/settings", json={"llmProvider": "anthropic", "anthropicApiKey": ""}, headers=headers)
    appconfig.reset()
    assert isinstance(llm._build_from_config(), FakeLLMClient)
