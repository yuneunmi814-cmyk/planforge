"""LLM client. A swappable interface so the worker is provider-agnostic and so
tests/dev can run with no API key.

- AnthropicClient: the real engine (lazy-imports the `anthropic` SDK).
- FakeLLMClient: deterministic, dependency-free stub. Emits a valid generation
  payload that satisfies the output contract (design §5.1) — and demonstrates
  the injection-defence path by *rejecting* obviously hostile/empty ideas.

Selection: settings.llm_provider == "anthropic" with an API key → real;
otherwise → fake (so the pipeline works end-to-end out of the box)."""

from __future__ import annotations

import json
from typing import Protocol

from app.core.config import get_settings
from app.models import SECTION_TYPES

settings = get_settings()


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, temperature: float, max_tokens: int) -> str:
        """Return the model's raw text output (expected to be a JSON string)."""
        ...


class AnthropicClient:
    """Cloud engine (best quality). Requires the user's API key."""

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic  # lazy: only required when actually using the real engine

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, *, system: str, user: str, temperature: float, max_tokens: int) -> str:
        msg = self._client.messages.create(
            model=self._model,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": user}],
        )
        # Concatenate text blocks; the prompt forbids non-JSON text, so this is
        # the JSON payload (possibly with a stray code fence — handled on parse).
        return "".join(block.text for block in msg.content if block.type == "text")


class OllamaClient:
    """Local engine (Meetily-style). No API key, runs on the user's machine via
    Ollama at localhost:11434. format=json nudges valid JSON for our contract."""

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def complete(self, *, system: str, user: str, temperature: float, max_tokens: int) -> str:
        import httpx

        resp = httpx.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=settings.ollama_timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


class FakeLLMClient:
    """Deterministic stub. Honours the security contract enough to be useful in
    tests: hostile/empty ideas are rejected, everything else yields 9 sections."""

    _REJECT_MARKERS = ("이전 지시 무시", "ignore previous", "system prompt", "프롬프트 출력")

    def complete(self, *, system: str, user: str, temperature: float, max_tokens: int) -> str:
        # Refine calls carry a <user_request>; generation calls carry <user_idea>.
        if "<user_request>" in user:
            return self._refine(user)
        idea = _extract_idea(user)
        lowered = idea.lower()
        if not idea.strip() or any(m.lower() in lowered for m in self._REJECT_MARKERS):
            return json.dumps(
                {"status": "rejected", "reason": "유효하지 않거나 부적절한 아이디어입니다."},
                ensure_ascii=False,
            )
        sections = [
            {
                "type": t,
                "title": f"{t} (stub)",
                "markdown": f"# {t}\n\n(FakeLLMClient) 아이디어: {idea[:80]}",
            }
            for t in SECTION_TYPES
        ]
        return json.dumps(
            {
                "status": "success",
                "assumed_stack": {
                    "frontend": settings.default_frontend,
                    "backend": settings.default_backend,
                    "db": settings.default_db,
                    "auth": settings.default_auth,
                },
                "sections": sections,
            },
            ensure_ascii=False,
        )

    def _refine(self, user: str) -> str:
        section_type = _extract_tag(user, "section_type") or _extract_bracket_type(user)
        request = _extract_tag(user, "user_request")
        lowered = request.lower()
        if not request.strip() or any(m.lower() in lowered for m in self._REJECT_MARKERS):
            return json.dumps(
                {"status": "rejected", "reason": "유효하지 않거나 부적절한 수정 요청입니다."},
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "status": "success",
                "type": section_type,
                "markdown": f"# {section_type} (refined)\n\n반영한 요청: {request[:80]}",
            },
            ensure_ascii=False,
        )


def _extract_tag(user: str, tag: str) -> str:
    open_t, close_t = f"<{tag}>", f"</{tag}>"
    start, end = user.find(open_t), user.find(close_t)
    if start == -1 or end == -1:
        return ""
    return user[start + len(open_t) : end].strip()


def _extract_idea(user: str) -> str:
    return _extract_tag(user, "user_idea") or user.strip()


def _extract_bracket_type(user: str) -> str:
    """Parse the '[섹션 타입] overview' line from a refine input contract."""
    for line in user.splitlines():
        line = line.strip()
        if line.startswith("[섹션 타입]"):
            return line.split("]", 1)[1].strip()
    return ""


_client: LLMClient | None = None


def _build_from_config() -> LLMClient:
    """Pick the engine from the runtime settings (services/appconfig.py):
    Ollama (local) by default, Anthropic when a key is set, else the fake stub."""
    from app.services.appconfig import get_config

    cfg = get_config()
    provider = cfg.get("llmProvider")
    if provider == "anthropic" and cfg.get("anthropicApiKey"):
        return AnthropicClient(cfg["anthropicApiKey"], cfg.get("anthropicModel") or settings.llm_model)
    if provider == "ollama":
        return OllamaClient(cfg.get("ollamaBaseUrl") or settings.ollama_base_url, cfg.get("ollamaModel") or settings.ollama_model)
    return FakeLLMClient()


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = _build_from_config()
    return _client


def set_llm(client: LLMClient | None) -> None:
    """Override the active client (tests; also called on settings change to force
    a rebuild on the next get_llm())."""
    global _client
    _client = client
