from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import Base, engine
from app.core.errors import register_error_handlers
from app.core import i18n
from app.routers import account, admin, auth, projects, settings as settings_router, usage

settings = get_settings()

# Scaffold convenience: create tables on startup. Use Alembic in production.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PlanForge — 아이디어 한 줄을 기획·설계 문서로",
    version="0.1.0",
    description="비동기 LLM 생성 파이프라인(Redis 큐 + 워커)으로 기획 설계 문서를 생성한다.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)


@app.middleware("http")
async def set_request_language(request: Request, call_next):
    """Resolve the request language from Accept-Language for localized errors."""
    token = i18n.current_lang.set(i18n.resolve_lang(request.headers.get("Accept-Language")))
    try:
        return await call_next(request)
    finally:
        i18n.current_lang.reset(token)


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(admin.router)
app.include_router(usage.router)
app.include_router(account.router)
app.include_router(settings_router.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
