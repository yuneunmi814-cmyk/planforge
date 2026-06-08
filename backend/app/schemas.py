from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


# ---- Auth ------------------------------------------------------------------
class SignupReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    accessToken: str
    refreshToken: str
    role: str
    status: str


class RefreshReq(BaseModel):
    refreshToken: str


class AccessTokenRes(BaseModel):
    accessToken: str


class UserRes(BaseModel):
    id: int
    email: EmailStr
    role: str
    status: str

    class Config:
        from_attributes = True


# ---- Projects / generation -------------------------------------------------
class ProjectCreateReq(BaseModel):
    # The one-line idea (design §2). Stored as data; never executed.
    idea: str = Field(min_length=1, max_length=2000)
    title: str | None = Field(default=None, max_length=255)
    # Optional stack overrides; omit to accept the defaults.
    frontend: str | None = None
    backend: str | None = None
    db: str | None = None
    auth: str | None = None


class RefineReq(BaseModel):
    # Free-text revision request. Treated as data; the refine system prompt
    # isolates it inside <user_request> for injection defence (design §refine).
    userRequest: str = Field(min_length=1, max_length=2000)


class JobRes(BaseModel):
    """Returned by the async accept (202) and by status polling."""

    jobId: int
    projectId: int
    kind: str
    status: str
    sectionType: str | None = None
    errorMessage: str | None = None
    createdAt: datetime
    finishedAt: datetime | None = None


class SectionRes(BaseModel):
    type: str
    title: str
    markdown: str
    version: int


class ProjectRes(BaseModel):
    id: int
    title: str
    idea: str
    assumedStack: dict | None = None
    createdAt: datetime
    latestJob: JobRes | None = None
    sections: list[SectionRes] = []
    # Canonical section types not present yet — non-empty means a weak model
    # produced a partial document (UI surfaces a hint to use a better engine).
    missingSections: list[str] = []


class ProjectSummaryRes(BaseModel):
    id: int
    title: str
    createdAt: datetime
    status: str  # latest job status, or "empty"


class PageRes(BaseModel):
    """Design §api_spec: list responses are paginated ({items,total,page})."""

    items: list[ProjectSummaryRes]
    total: int
    page: int
    pageSize: int


class OkRes(BaseModel):
    ok: bool = True


# ---- Settings (LLM engine: Ollama default / Anthropic optional) ------------
class SettingsRes(BaseModel):
    llmProvider: str  # ollama | anthropic | fake
    ollamaBaseUrl: str
    ollamaModel: str
    anthropicModel: str
    hasAnthropicKey: bool
    anthropicKeyMasked: str  # e.g. "••••abcd", never the full key


class SettingsUpdateReq(BaseModel):
    llmProvider: Literal["ollama", "anthropic", "fake"] | None = None
    ollamaBaseUrl: str | None = None
    ollamaModel: str | None = None
    anthropicApiKey: str | None = None
    anthropicModel: str | None = None


class OllamaPullReq(BaseModel):
    model: str | None = None  # defaults to the configured ollamaModel


# ---- Account (PF-5) --------------------------------------------------------
class AccountDeleteRes(BaseModel):
    """Transparency: what was purged immediately vs legally retained."""

    purged: list[str]
    retained: list[str]


# ---- Admin (PF-3) ----------------------------------------------------------
class AdminUserRes(BaseModel):
    id: int
    email: EmailStr
    role: str
    status: str
    createdAt: datetime


class AdminUserPageRes(BaseModel):
    items: list[AdminUserRes]
    total: int
    page: int
    pageSize: int


class AdminUserUpdateReq(BaseModel):
    status: Literal["pending", "approved", "disabled"] | None = None
    role: Literal["admin", "user"] | None = None

    @model_validator(mode="after")
    def _require_one(self) -> "AdminUserUpdateReq":
        if self.status is None and self.role is None:
            raise ValueError("status 또는 role 중 하나는 필요합니다.")
        return self


class AdminJobRes(BaseModel):
    jobId: int
    projectId: int
    userId: int
    kind: str
    status: str
    sectionType: str | None = None
    promptVersion: str | None = None
    attempts: int
    createdAt: datetime
    finishedAt: datetime | None = None


class AdminJobStats(BaseModel):
    counts: dict[str, int]  # status → count
    total: int
    failureRate: float  # failed / (success + rejected + failed)


class AdminJobsRes(BaseModel):
    stats: AdminJobStats
    items: list[AdminJobRes]
    total: int
    page: int
    pageSize: int


class PromptInfoRes(BaseModel):
    name: str  # "generate" | "refine"
    filename: str
    version: str  # content hash
    chars: int


# ---- Usage / billing (PF-4) ------------------------------------------------
class UsageRes(BaseModel):
    plan: str  # free | pro
    limitPerMinute: int
    today: int  # jobs run today (UTC)
    total: int
    byStatus: dict[str, int]


class AdminUsageRes(BaseModel):
    total: int
    byStatus: dict[str, int]
    byKind: dict[str, int]
    topUsers: list[dict]  # [{userId, count}]
