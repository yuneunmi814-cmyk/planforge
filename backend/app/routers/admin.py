"""Admin API (design §admin_flow).

Covers: 사용자 관리(상태 조회·승인·제재), 운영 모니터링(잡 현황·실패율),
시스템 제어(로드된 프롬프트 버전 확인). All endpoints require role=admin (RBAC).
Prompt *editing* is intentionally out of scope — the prompts/ files are the SSOT.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_role
from app.models import GenerationJob, UsageLog, User
from app.schemas import (
    AdminJobRes,
    AdminJobsRes,
    AdminJobStats,
    AdminUsageRes,
    AdminUserPageRes,
    AdminUserRes,
    AdminUserUpdateReq,
    PromptInfoRes,
)
from app.services import audit, prompts
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
settings = get_settings()

_FAILURE_DENOMINATOR = ("success", "rejected", "failed")


def _user_res(u: User) -> AdminUserRes:
    return AdminUserRes(
        id=u.id, email=u.email, role=u.role, status=u.status, createdAt=u.created_at
    )


@router.get("/users", response_model=AdminUserPageRes)
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
) -> AdminUserPageRes:
    base = select(User)
    if status_filter:
        base = base.where(User.status == status_filter)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(
        base.order_by(User.id.asc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return AdminUserPageRes(
        items=[_user_res(u) for u in rows],
        total=int(total or 0),
        page=page,
        pageSize=page_size,
    )


@router.patch("/users/{user_id}", response_model=AdminUserRes)
def update_user(
    user_id: int,
    body: AdminUserUpdateReq,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
) -> AdminUserRes:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    # Lockout guard: an admin cannot demote or disable their own account.
    if user.id == admin.id and (
        (body.role is not None and body.role != "admin")
        or (body.status is not None and body.status != "approved")
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="cannot_modify_self"
        )

    changes: dict = {}
    if body.status is not None and body.status != user.status:
        changes["status"] = {"from": user.status, "to": body.status}
        user.status = body.status
    if body.role is not None and body.role != user.role:
        changes["role"] = {"from": user.role, "to": body.role}
        user.role = body.role
    db.commit()
    db.refresh(user)

    if changes:
        audit.record(
            db,
            actor_user_id=admin.id,
            action="admin.user.update",
            target_type="user",
            target_id=user.id,
            detail=changes,
        )
    return _user_res(user)


@router.get("/jobs", response_model=AdminJobsRes)
def list_jobs(
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
) -> AdminJobsRes:
    # Aggregate counts across ALL jobs (not just the page) for the dashboard.
    count_rows = db.execute(
        select(GenerationJob.status, func.count()).group_by(GenerationJob.status)
    ).all()
    counts = {s: int(c) for s, c in count_rows}
    total = sum(counts.values())
    denom = sum(counts.get(s, 0) for s in _FAILURE_DENOMINATOR)
    failure_rate = (counts.get("failed", 0) / denom) if denom else 0.0
    stats = AdminJobStats(counts=counts, total=total, failureRate=round(failure_rate, 4))

    base = select(GenerationJob)
    if status_filter:
        base = base.where(GenerationJob.status == status_filter)
    page_total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(
        base.order_by(GenerationJob.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        AdminJobRes(
            jobId=j.id,
            projectId=j.project_id,
            userId=j.user_id,
            kind=j.kind,
            status=j.status,
            sectionType=j.section_type,
            promptVersion=j.prompt_version,
            attempts=j.attempts,
            createdAt=j.created_at,
            finishedAt=j.finished_at,
        )
        for j in rows
    ]
    return AdminJobsRes(
        stats=stats, items=items, total=int(page_total or 0), page=page, pageSize=page_size
    )


@router.get("/usage", response_model=AdminUsageRes)
def usage_overview(
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
    top: int = Query(5, ge=1, le=50),
) -> AdminUsageRes:
    total = db.scalar(select(func.count()).select_from(UsageLog)) or 0
    by_status = {
        s: int(c)
        for s, c in db.execute(
            select(UsageLog.status, func.count()).group_by(UsageLog.status)
        ).all()
    }
    by_kind = {
        k: int(c)
        for k, c in db.execute(
            select(UsageLog.kind, func.count()).group_by(UsageLog.kind)
        ).all()
    }
    top_rows = db.execute(
        select(UsageLog.user_id, func.count().label("c"))
        .group_by(UsageLog.user_id)
        .order_by(func.count().desc())
        .limit(top)
    ).all()
    return AdminUsageRes(
        total=int(total),
        byStatus=by_status,
        byKind=by_kind,
        topUsers=[{"userId": uid, "count": int(c)} for uid, c in top_rows],
    )


@router.get("/prompts", response_model=list[PromptInfoRes])
def list_prompts(admin: User = Depends(require_role("admin"))) -> list[PromptInfoRes]:
    """Show which prompt files are loaded and their content-hash version
    (design 1.2: 프롬프트 버전 관리). The files themselves remain the SSOT."""
    gen_text, gen_ver = prompts.generation_system_prompt()
    ref_text, ref_ver = prompts.refine_system_prompt()
    return [
        PromptInfoRes(
            name="generate",
            filename=settings.prompt_file_generate,
            version=gen_ver,
            chars=len(gen_text),
        ),
        PromptInfoRes(
            name="refine",
            filename=settings.prompt_file_refine,
            version=ref_ver,
            chars=len(ref_text),
        ),
    ]
