"""PlanForge ORM models.

The async generation pipeline turns one Project (an "idea + assumed stack")
into a GenerationJob, which the worker processes by calling the LLM and parsing
its structured output into per-type Section rows (design §5 output contract,
§10 worker). Sections are versioned (is_latest) so /refine can replace a single
section without touching the rest. AuditLog is append-only (design admin_flow:
operation monitoring / prompt-version traceability)."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# The 13 sections the generation prompt must emit, in order (design §5.1 / §6).
SECTION_TYPES = (
    "overview",
    "user_flow",
    "admin_flow",
    "db_schema",
    "security",
    "privacy_law",
    "api_spec",
    "architecture",
    "crud_mapping",
    # Production-grade sections (top-tier design doc).
    "nfr",
    "testing",
    "deployment",
    "risks",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # admin | user
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | approved | disabled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    projects: Mapped[list["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Project(Base):
    """A single planning request: the user's one-line idea + assumed stack."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    # The raw user idea. Treated as DATA, never as instructions (injection
    # defence lives in the system prompt — design §3).
    idea: Mapped[str] = mapped_column(Text)
    # Requested stack; NULL means "use the default" (design §2 auto-fill).
    frontend: Mapped[str | None] = mapped_column(String(255), nullable=True)
    backend: Mapped[str | None] = mapped_column(String(255), nullable=True)
    db: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The stack actually assumed by the model, as returned in assumed_stack.
    assumed_stack: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Soft Delete (design §6 db_schema / crud_mapping)

    user: Mapped["User"] = relationship(back_populates="projects")
    jobs: Mapped[list["GenerationJob"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    sections: Mapped[list["Section"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class GenerationJob(Base):
    """One async LLM run for a project. The worker drives status transitions."""

    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="generate")  # generate | refine
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    # queued | running | success | rejected | failed
    # For kind=refine: which section is being rewritten (design §refine).
    section_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # For kind=refine: the user's revision request (data, never instructions).
    user_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Pin which prompt version produced the output (admin: prompt version mgmt).
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # On rejected/failed: the reason surfaced to the user (sanitised).
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="jobs")


class Section(Base):
    """One parsed section of the generated document, versioned for /refine.

    Only one row per (project, type) carries is_latest=True; older versions are
    retained for history (design §6 db_schema: 이력 보존)."""

    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("project_id", "type", "version", name="uq_section_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)  # one of SECTION_TYPES
    title: Mapped[str] = mapped_column(String(255))
    markdown: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped["Project"] = relationship(back_populates="sections")


class UsageLog(Base):
    """Per-job usage record for billing/quota accounting (design §db_schema:
    과금/사용량 서비스는 usage_logs 누락 금지). Append-only."""

    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("generation_jobs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))  # generate | refine
    status: Mapped[str] = mapped_column(String(16))  # success | rejected | failed
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class Subscription(Base):
    """Billing plan per user (design §db_schema: subscriptions). Soft-deletable.
    Note: payment integration is out of scope — this records the plan only."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(16), default="free")  # free | pro
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | canceled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Append-only audit trail. No updates/deletes in normal operation."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
