"""Multi-provider engine selection + settings round-trip for the new OpenAI and
Gemini API-key engines."""

import pytest

from app.services import appconfig, llm
from app.services.llm import (
    AnthropicClient,
    FakeLLMClient,
    GeminiClient,
    OllamaClient,
    OpenAIClient,
)
from tests.conftest import auth_headers


@pytest.mark.parametrize(
    "cfg,expected",
    [
        ({"llmProvider": "openai", "openaiApiKey": "sk-x", "openaiModel": "gpt-4o"}, OpenAIClient),
        ({"llmProvider": "gemini", "geminiApiKey": "g-x", "geminiModel": "gemini-1.5-pro"}, GeminiClient),
        ({"llmProvider": "anthropic", "anthropicApiKey": "a-x", "anthropicModel": "m"}, AnthropicClient),
        ({"llmProvider": "ollama", "ollamaBaseUrl": "http://x", "ollamaModel": "y"}, OllamaClient),
        # A selected cloud provider with no key falls back to the stub (no crash).
        ({"llmProvider": "openai", "openaiApiKey": ""}, FakeLLMClient),
    ],
)
def test_build_from_config_selects_client(monkeypatch, cfg, expected):
    monkeypatch.setattr(appconfig, "get_config", lambda: cfg)
    try:
        assert isinstance(llm._build_from_config(), expected)
    finally:
        llm.set_llm(None)


def test_settings_openai_gemini_roundtrip(client):
    headers = auth_headers(client)
    res = client.put(
        "/api/v1/settings",
        json={"llmProvider": "openai", "openaiApiKey": "sk-secret-1234", "openaiModel": "gpt-4o"},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["llmProvider"] == "openai"
    assert body["hasOpenaiKey"] is True
    # The full key is never returned — only a masked hint ending in the last 4.
    assert body["openaiKeyMasked"].endswith("1234")
    assert "secret" not in body["openaiKeyMasked"]
    assert body["hasGeminiKey"] is False
