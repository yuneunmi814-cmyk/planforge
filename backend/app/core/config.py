from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# prompts/ lives at the PlanForge project root (sibling of backend/). The worker
# loads the system prompts from there at runtime so the docs stay the single
# source of truth — see services/prompts.py.
#   config.py -> core -> app -> backend -> planforge(root)/prompts
_PROMPTS_DIR_DEFAULT = str(Path(__file__).resolve().parents[3] / "prompts")


class Settings(BaseSettings):
    """Runtime configuration. All values come from env (prefix PLANFORGE_)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PLANFORGE_", extra="ignore")

    # --- Database ---
    # SQLite for local dev/test; set to Postgres in prod / docker-compose.
    database_url: str = "sqlite:///./planforge.db"

    # --- Auth (JWT) ---
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 14

    # --- Dispatch mode ---
    # inline_dispatch=True runs the generation in-process (FastAPI BackgroundTasks),
    # no Redis/worker needed — handy for local/single-user setups. Production uses
    # the Redis queue + a separate worker process.
    inline_dispatch: bool = False

    # --- Redis job queue ---
    redis_url: str = "redis://localhost:6379/0"
    job_queue_name: str = "planforge:jobs"

    # --- Progress events (SSE) ---
    job_event_key_prefix: str = "planforge:jobevents:"
    job_event_ttl_seconds: int = 3600  # event history expiry
    sse_poll_interval_seconds: float = 0.5  # how often the stream tails history
    sse_max_seconds: int = 120  # safety cap so a stuck job can't stream forever

    # --- LLM (generation engine) ---
    # provider: "ollama" (local, no key), "anthropic" (cloud key), or "fake"
    # (deterministic stub for dev/tests). This is the DEFAULT seed; the desktop
    # app overrides it at runtime via the settings store (services/appconfig.py).
    # Backend default stays "anthropic"; the desktop sidecar sets it to "ollama".
    llm_provider: str = "anthropic"
    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-4-6"

    # Ollama (local LLM, Meetily-style — no API key, runs on the user's machine).
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    ollama_timeout_seconds: int = 180
    # Design §8: planning docs favour consistency over creativity, big output.
    llm_temperature: float = 0.4
    llm_max_tokens: int = 8192
    # Design §10: parse failure → 1 retry, then mark the job failed.
    llm_parse_max_attempts: int = 2

    # --- Prompts (single source of truth = the prompts/ folder) ---
    prompts_dir: str = _PROMPTS_DIR_DEFAULT
    prompt_file_generate: str = "PlanForge_시스템프롬프트_실전투입용.md"
    prompt_file_refine: str = "PlanForge_시스템프롬프트_재수정용.md"

    # --- Rate limiting (design §api_spec: 429; checklist #6) ---
    # Fixed-window per-user limit on heavy LLM endpoints (generate/refine).
    generate_rate_limit_per_minute: int = 10
    rate_limit_window_seconds: int = 60

    # --- Default stack (design §2 — assumed when the user leaves a field blank) ---
    default_frontend: str = "React + TypeScript"
    default_backend: str = "Python / FastAPI"
    default_db: str = "PostgreSQL"
    default_auth: str = "JWT(Access/Refresh) + Bcrypt + AES-256"

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
