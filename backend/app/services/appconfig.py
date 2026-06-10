"""Runtime, user-editable settings persisted to ~/.planforge/config.json.

Unlike core.config.Settings (env-driven, read once at startup), this holds
values the *end user* changes from the desktop settings screen — chiefly which
LLM engine to use and the credentials/model for it. Changing it rebuilds the
active LLM client (see services/llm.py)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()

# Field names are camelCase to match the JSON API surface directly.
PROVIDERS = ("ollama", "anthropic", "openai", "gemini", "fake")


def _defaults() -> dict:
    return {
        # Seeded from env so the desktop sidecar (PLANFORGE_LLM_PROVIDER=ollama)
        # and the plain backend (anthropic) each get a sensible default.
        "llmProvider": settings.llm_provider,
        "ollamaBaseUrl": settings.ollama_base_url,
        "ollamaModel": settings.ollama_model,
        "anthropicApiKey": settings.anthropic_api_key or "",
        "anthropicModel": settings.llm_model,
        "openaiApiKey": settings.openai_api_key or "",
        "openaiModel": settings.openai_model,
        "geminiApiKey": settings.gemini_api_key or "",
        "geminiModel": settings.gemini_model,
    }


def config_path() -> Path:
    base = Path(os.environ.get("PLANFORGE_DATA_DIR", Path.home() / ".planforge"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "config.json"


_cache: dict | None = None


def get_config() -> dict:
    global _cache
    if _cache is None:
        data = _defaults()
        path = config_path()
        if path.is_file():
            try:
                data.update(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                pass  # corrupt/unreadable → fall back to defaults
        _cache = data
    return dict(_cache)


def update_config(patch: dict) -> dict:
    """Merge non-null fields, persist, and force the LLM client to rebuild."""
    cfg = get_config()
    for key, value in patch.items():
        if value is not None and key in _defaults():
            cfg[key] = value
    config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    global _cache
    _cache = cfg

    from app.services import llm  # lazy to avoid import cycle

    llm.set_llm(None)  # next get_llm() picks up the new config
    return dict(cfg)


def reset() -> None:
    """Drop the in-memory cache (used by tests)."""
    global _cache
    _cache = None
