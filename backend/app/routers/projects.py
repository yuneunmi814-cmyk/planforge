"""Projects + async generation API (design §api_spec).

Heavy work (the LLM call) is never done in the request. Creating a project
returns 202 Accepted + a job_id; the client polls the job until it reaches a
terminal state, then fetches the project's sections."""

import json
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.core.ratelimit import get_rate_limiter
from app.core.security import decode_token, get_approved_user
from app.models import SECTION_TYPES, GenerationJob, Project, Section, User
from app.services.events import TERMINAL_EVENTS, get_event_bus
from app.schemas import (
    JobRes,
    PageRes,
    ProjectCreateReq,
    ProjectRes,
    ProjectSummaryRes,
    RefineReq,
    SectionRes,
)
from app.services import audit
from app.services.queue import get_queue

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
settings = get_settings()


def _run_inline(job_id: int) -> None:
    """Process a job in-process (no Redis/worker). Uses its own DB session.

    Dispatches by job kind so both generate and refine work inline."""
    from app.worker.processor import process_job

    with SessionLocal() as db:
        process_job(db, job_id)


def _enforce_rate_limit(user_id: int) -> None:
    """Throttle heavy LLM endpoints per user → 429 + Retry-After (design §api_spec)."""
    allowed, retry_after = get_rate_limiter().hit(
        f"gen:{user_id}",
        settings.generate_rate_limit_per_minute,
        settings.rate_limit_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate_limited",
            headers={"Retry-After": str(retry_after)},
        )


def _dispatch(background: BackgroundTasks, job: GenerationJob) -> None:
    """Send a job to the worker — inline (BackgroundTasks) or Redis queue."""
    if settings.inline_dispatch:
        background.add_task(_run_inline, job.id)
    else:
        get_queue().enqueue({"jobId": job.id, "kind": job.kind})


def _job_res(job: GenerationJob) -> JobRes:
    return JobRes(
        jobId=job.id,
        projectId=job.project_id,
        kind=job.kind,
        status=job.status,
        sectionType=job.section_type,
        errorMessage=job.error_message,
        createdAt=job.created_at,
        finishedAt=job.finished_at,
    )


def _latest_job(db: Session, project_id: int) -> GenerationJob | None:
    return db.scalar(
        select(GenerationJob)
        .where(GenerationJob.project_id == project_id)
        .order_by(GenerationJob.id.desc())
        .limit(1)
    )


def get_streaming_user(
    request: Request,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Auth for SSE. Browser EventSource can't send Authorization headers, so an
    approved access token may be supplied via ?token= (header still works too)."""
    raw = token
    if not raw:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            raw = header[len("Bearer ") :]
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required")
    payload = decode_token(raw)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_access_token")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
    if user.status != "approved" and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account_pending")
    return user


def _owned_project(db: Session, project_id: int, user: User) -> Project:
    project = db.get(Project, project_id)
    if not project or project.user_id != user.id or project.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")
    return project


@router.post("", response_model=JobRes, status_code=status.HTTP_202_ACCEPTED)
def create_project(
    body: ProjectCreateReq,
    response: Response,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_approved_user),
) -> JobRes:
    _enforce_rate_limit(user.id)
    project = Project(
        user_id=user.id,
        title=body.title or body.idea[:60],
        idea=body.idea,
        frontend=body.frontend,
        backend=body.backend,
        db=body.db,
        auth=body.auth,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    job = GenerationJob(project_id=project.id, user_id=user.id, kind="generate", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    _dispatch(background, job)

    audit.record(
        db,
        actor_user_id=user.id,
        action="project.create",
        target_type="project",
        target_id=project.id,
        detail={"jobId": job.id},
    )

    response.headers["Location"] = f"/api/v1/projects/{project.id}/jobs/{job.id}"
    return _job_res(job)


@router.get("/{project_id}/jobs/{job_id}", response_model=JobRes)
def get_job(
    project_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_approved_user),
) -> JobRes:
    _owned_project(db, project_id, user)
    job = db.get(GenerationJob, job_id)
    if not job or job.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    return _job_res(job)


def _sse_stream(job_id: int):
    """Replay a job's event history, then tail new events until terminal (design
    §user_flow: 진행률·점진 노출). A safety cap prevents a stuck job streaming
    forever."""
    bus = get_event_bus()
    sent = 0
    elapsed = 0.0
    interval = settings.sse_poll_interval_seconds
    yield ": connected\n\n"  # open the stream immediately
    while elapsed <= settings.sse_max_seconds:
        events = bus.history(job_id)
        for ev in events[sent:]:
            yield f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        sent = len(events)
        if events and events[-1]["type"] in TERMINAL_EVENTS:
            return
        time.sleep(interval)
        elapsed += interval


@router.get("/{project_id}/jobs/{job_id}/events")
def stream_job_events(
    project_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_streaming_user),
) -> StreamingResponse:
    _owned_project(db, project_id, user)
    job = db.get(GenerationJob, job_id)
    if not job or job.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    return StreamingResponse(
        _sse_stream(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{project_id}/sections/{section_type}/refine",
    response_model=JobRes,
    status_code=status.HTTP_202_ACCEPTED,
)
def refine_section(
    project_id: int,
    section_type: str,
    body: RefineReq,
    response: Response,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_approved_user),
) -> JobRes:
    """Rewrite a single section per a user revision request (design §refine).

    Async like generation: returns 202 + jobId; the worker calls the refine
    prompt and stores a new version of just this section."""
    _enforce_rate_limit(user.id)
    project = _owned_project(db, project_id, user)
    if section_type not in SECTION_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_section_type")

    current = db.scalar(
        select(Section)
        .where(
            Section.project_id == project.id,
            Section.type == section_type,
            Section.is_latest.is_(True),
        )
        .limit(1)
    )
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="section_not_generated"
        )

    # Persist the revision request on the job so the worker (even after a
    # restart) has the full input without relying on the queue payload.
    job = GenerationJob(
        project_id=project.id,
        user_id=user.id,
        kind="refine",
        status="queued",
        section_type=section_type,
        user_request=body.userRequest,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    _dispatch(background, job)

    audit.record(
        db,
        actor_user_id=user.id,
        action="section.refine",
        target_type="section",
        target_id=f"{project.id}:{section_type}",
        detail={"jobId": job.id},
    )

    response.headers["Location"] = f"/api/v1/projects/{project.id}/jobs/{job.id}"
    return _job_res(job)


@router.get("/{project_id}", response_model=ProjectRes)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_approved_user),
) -> ProjectRes:
    project = _owned_project(db, project_id, user)
    sections = db.scalars(
        select(Section)
        .where(Section.project_id == project_id, Section.is_latest.is_(True))
        .order_by(Section.id.asc())
    ).all()
    latest = _latest_job(db, project_id)
    return ProjectRes(
        id=project.id,
        title=project.title,
        idea=project.idea,
        assumedStack=json.loads(project.assumed_stack) if project.assumed_stack else None,
        createdAt=project.created_at,
        latestJob=_job_res(latest) if latest else None,
        sections=[
            SectionRes(type=s.type, title=s.title, markdown=s.markdown, version=s.version)
            for s in sections
        ],
    )


def _ordered_latest_sections(db: Session, project_id: int) -> list[Section]:
    sections = db.scalars(
        select(Section).where(Section.project_id == project_id, Section.is_latest.is_(True))
    ).all()
    order = {t: i for i, t in enumerate(SECTION_TYPES)}
    return sorted(sections, key=lambda s: order.get(s.type, len(order)))


@router.get("/{project_id}/export")
def export_project(
    project_id: int,
    format: str = Query("md", pattern="^(md|json)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_approved_user),
):
    """Export the assembled document (latest sections, design §5 order) as a
    downloadable markdown or JSON file."""
    project = _owned_project(db, project_id, user)
    sections = _ordered_latest_sections(db, project.id)
    assumed = json.loads(project.assumed_stack) if project.assumed_stack else None
    filename = f"planforge-{project.id}.{format}"
    disposition = {"Content-Disposition": f'attachment; filename="{filename}"'}

    if format == "json":
        return JSONResponse(
            content={
                "id": project.id,
                "title": project.title,
                "idea": project.idea,
                "assumedStack": assumed,
                "sections": [
                    {"type": s.type, "title": s.title, "markdown": s.markdown, "version": s.version}
                    for s in sections
                ],
            },
            headers=disposition,
        )

    lines = [f"# {project.title}", "", f"> {project.idea}", ""]
    if assumed:
        lines.append("**가정한 스택**: " + ", ".join(f"{k}={v}" for k, v in assumed.items()))
        lines.append("")
    for s in sections:
        lines.append(f"## {s.title}")
        lines.append("")
        lines.append(s.markdown)
        lines.append("")
    return Response(
        content="\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers=disposition,
    )


@router.get("", response_model=PageRes)
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_approved_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageRes:
    base = select(Project).where(Project.user_id == user.id, Project.deleted_at.is_(None))
    total = len(db.scalars(base).all())
    rows = db.scalars(
        base.order_by(Project.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = []
    for p in rows:
        latest = _latest_job(db, p.id)
        items.append(
            ProjectSummaryRes(
                id=p.id,
                title=p.title,
                createdAt=p.created_at,
                status=latest.status if latest else "empty",
            )
        )
    return PageRes(items=items, total=total, page=page, pageSize=page_size)
