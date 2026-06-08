"""Prompt loading + input-contract assembly.

The system prompts are NOT duplicated in code — they are read from the prompts/
folder (the single source of truth the design doc curates). The worker injects
the loaded text verbatim as the LLM *system* message and assembles the user
message per the Input Contract (design §2), keeping the user's free-text idea
isolated inside <user_idea> for injection defence (design §3)."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


class PromptNotFoundError(RuntimeError):
    pass


@lru_cache(maxsize=8)
def _load(filename: str) -> tuple[str, str]:
    """Return (text, version). version = short content hash, used to pin which
    prompt produced a job's output (admin: prompt version management)."""
    path = Path(settings.prompts_dir) / filename
    if not path.is_file():
        raise PromptNotFoundError(f"system prompt not found: {path}")
    text = path.read_text(encoding="utf-8")
    version = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return text, version


def generation_system_prompt() -> tuple[str, str]:
    """The full generation system prompt + its version tag."""
    return _load(settings.prompt_file_generate)


def refine_system_prompt() -> tuple[str, str]:
    """The single-section refine system prompt + its version tag."""
    return _load(settings.prompt_file_refine)


def build_generation_input(
    *,
    idea: str,
    frontend: str | None = None,
    backend: str | None = None,
    db: str | None = None,
    auth: str | None = None,
) -> str:
    """Assemble the user message for a generation call (design §2 Input Contract).

    Blank stack fields fall back to the configured defaults. The raw idea is
    placed inside <user_idea> and never interpreted as instructions — the system
    prompt's security rules enforce that."""
    fe = frontend or settings.default_frontend
    be = backend or settings.default_backend
    database = db or settings.default_db
    au = auth or settings.default_auth
    return (
        "[프로젝트 기본 정보]\n"
        f"- Frontend: {fe}\n"
        f"- Backend:  {be}\n"
        f"- DB:       {database}\n"
        f"- 인증/보안: {au}\n\n"
        "<user_idea>\n"
        f"{idea}\n"
        "</user_idea>\n"
    )


def build_refine_input(
    *,
    section_type: str,
    current_content: str,
    user_request: str,
    frontend: str | None = None,
    backend: str | None = None,
    db: str | None = None,
    auth: str | None = None,
) -> str:
    """Assemble the user message for a single-section refine (design §refine)."""
    fe = frontend or settings.default_frontend
    be = backend or settings.default_backend
    database = db or settings.default_db
    au = auth or settings.default_auth
    return (
        f"[섹션 타입] {section_type}\n"
        f"[프로젝트 스택] frontend={fe}, backend={be}, db={database}, auth={au}\n\n"
        "<current_content>\n"
        f"{current_content}\n"
        "</current_content>\n\n"
        "<user_request>\n"
        f"{user_request}\n"
        "</user_request>\n"
    )
