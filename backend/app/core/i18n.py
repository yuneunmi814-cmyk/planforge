"""Backend message localization (KO/EN).

User-facing error messages are raised as stable KEYS (e.g. "invalid_credentials")
instead of literal text. The error handler translates the key into the request's
language, chosen from the Accept-Language header (the desktop app sends it based
on the in-app KO/EN toggle). Unknown keys pass through unchanged, so dynamic
text (e.g. an LLM rejection reason) is returned as-is."""

from __future__ import annotations

from contextvars import ContextVar

# Default to English for a global audience; the app flips this per request.
DEFAULT_LANG = "en"
SUPPORTED = ("en", "ko")

# Set per-request by the middleware in main.py.
current_lang: ContextVar[str] = ContextVar("current_lang", default=DEFAULT_LANG)

MESSAGES: dict[str, dict[str, str]] = {
    # auth / account
    "email_taken": {"en": "This email is already registered.", "ko": "이미 가입된 이메일입니다."},
    "invalid_credentials": {"en": "Incorrect email or password.", "ko": "이메일 또는 비밀번호가 올바르지 않습니다."},
    "account_disabled": {"en": "This account is disabled.", "ko": "비활성화된 계정입니다."},
    "account_pending": {"en": "Your account is awaiting approval.", "ko": "승인 대기 중인 계정입니다."},
    "user_not_found": {"en": "User not found.", "ko": "사용자를 찾을 수 없습니다."},
    "cannot_modify_self": {"en": "You cannot change your own role or status.", "ko": "자기 자신의 권한/상태는 변경할 수 없습니다."},
    # tokens
    "invalid_token": {"en": "Invalid token.", "ko": "유효하지 않은 토큰입니다."},
    "not_access_token": {"en": "Not an access token.", "ko": "액세스 토큰이 아닙니다."},
    "not_refresh_token": {"en": "Not a refresh token.", "ko": "리프레시 토큰이 아닙니다."},
    "auth_required": {"en": "Authentication required.", "ko": "인증이 필요합니다."},
    "forbidden_role": {"en": "You don't have permission to do that.", "ko": "권한이 없습니다."},
    # projects / generation
    "project_not_found": {"en": "Project not found.", "ko": "프로젝트를 찾을 수 없습니다."},
    "job_not_found": {"en": "Job not found.", "ko": "작업을 찾을 수 없습니다."},
    "unknown_section_type": {"en": "Unknown section type.", "ko": "존재하지 않는 섹션 타입입니다."},
    "section_not_generated": {"en": "This section hasn't been generated yet.", "ko": "아직 생성되지 않은 섹션은 수정할 수 없습니다."},
    "rate_limited": {"en": "Too many requests. Please try again shortly.", "ko": "요청이 너무 많습니다. 잠시 후 다시 시도하세요."},
    # generic (error envelope)
    "internal_error": {"en": "An internal server error occurred.", "ko": "서버 내부 오류가 발생했습니다."},
    "request_failed": {"en": "The request could not be processed.", "ko": "요청을 처리할 수 없습니다."},
    "invalid_input": {"en": "Invalid input.", "ko": "입력값이 유효하지 않습니다."},
}


def resolve_lang(accept_language: str | None) -> str:
    """Pick a supported language from an Accept-Language header (very small parse)."""
    if not accept_language:
        return DEFAULT_LANG
    for part in accept_language.split(","):
        code = part.split(";")[0].strip().lower()
        if code.startswith("ko"):
            return "ko"
        if code.startswith("en"):
            return "en"
    return DEFAULT_LANG


def translate(key: str | None, lang: str | None = None) -> str:
    """Translate a message key; pass through any non-key string unchanged."""
    if not key:
        return ""
    lang = lang or current_lang.get()
    entry = MESSAGES.get(key)
    if entry is None:
        return key  # dynamic/unknown text → return verbatim
    return entry.get(lang) or entry.get(DEFAULT_LANG, key)
