"""Job processing core (design §10 worker).

Separated from the queue loop so it can be unit-tested directly. `process_job`
dispatches by job kind:

  - generate: system prompt + input contract → LLM → parse 13-section output
    contract → store each section as a new latest version.
  - refine:   refine prompt + current section → LLM → parse single-section
    output → store a new version of just that section.

Both paths retry once on parse/transport failure (design §10), reject hostile/
invalid input, and write every outcome to the audit trail (log transparency)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import SECTION_TYPES, GenerationJob, Project, Section, UsageLog
from app.services import audit, prompts
from app.services.events import get_event_bus
from app.services.llm import get_llm

settings = get_settings()
log = logging.getLogger(__name__)

_TERMINAL = ("success", "rejected", "failed")


class OutputContractError(ValueError):
    """The model's output did not satisfy the JSON output contract (§5.1)."""


def _emit(job: GenerationJob, event_type: str, **extra) -> None:
    """Publish a progress event for this job (best-effort; never blocks work)."""
    try:
        get_event_bus().publish(job.id, {"type": event_type, "jobId": job.id, **extra})
    except Exception:  # noqa: BLE001 — telemetry must not break the pipeline
        log.warning("failed to publish %s event for job %s", event_type, job.id)


def process_job(db: Session, job_id: int) -> str:
    """Process one job (generate or refine). Returns the final job status."""
    job = db.get(GenerationJob, job_id)
    if job is None:
        return "missing"
    if job.status in _TERMINAL:
        return job.status

    project = db.get(Project, job.project_id)
    if project is None or project.deleted_at is not None:
        return _finish(db, job, "failed", "프로젝트를 찾을 수 없습니다.")

    job.status = "running"
    db.commit()
    _emit(job, "running", kind=job.kind)

    if job.kind == "refine":
        return _process_refine(db, job, project)
    return _process_generation(db, job, project)


# --- generate ---------------------------------------------------------------
def _process_generation(db: Session, job: GenerationJob, project: Project) -> str:
    system, version = prompts.generation_system_prompt()
    job.prompt_version = version
    user_msg = prompts.build_generation_input(
        idea=project.idea,
        frontend=project.frontend,
        backend=project.backend,
        db=project.db,
        auth=project.auth,
    )

    payload, last_error = _call_with_retries(db, job, system, user_msg, _parse_generation)
    if payload is None:
        return _finish(db, job, "failed", last_error)
    if payload.get("status") == "rejected":
        return _finish(db, job, "rejected", str(payload.get("reason", "거부됨"))[:500])

    _store_sections(db, project, payload["sections"])
    for s in payload["sections"]:
        _emit(job, "section_saved", section=s["type"])
    project.assumed_stack = json.dumps(payload.get("assumed_stack"), ensure_ascii=False)
    db.commit()
    return _finish(db, job, "success", None)


# --- refine -----------------------------------------------------------------
def _process_refine(db: Session, job: GenerationJob, project: Project) -> str:
    section_type = job.section_type
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
        return _finish(db, job, "failed", "수정할 섹션을 찾을 수 없습니다.")

    system, version = prompts.refine_system_prompt()
    job.prompt_version = version
    user_msg = prompts.build_refine_input(
        section_type=section_type,
        current_content=current.markdown,
        user_request=job.user_request or "",
        frontend=project.frontend,
        backend=project.backend,
        db=project.db,
        auth=project.auth,
    )

    payload, last_error = _call_with_retries(
        db, job, system, user_msg, lambda raw: _parse_refine(raw, section_type)
    )
    if payload is None:
        return _finish(db, job, "failed", last_error)
    if payload.get("status") == "rejected":
        return _finish(db, job, "rejected", str(payload.get("reason", "거부됨"))[:500])

    # Store only this section as a new version; other sections untouched.
    _store_sections(
        db, project, [{"type": section_type, "title": current.title, "markdown": payload["markdown"]}]
    )
    _emit(job, "section_saved", section=section_type)
    db.commit()
    return _finish(db, job, "success", None)


# --- shared LLM call + retry ------------------------------------------------
def _call_with_retries(
    db: Session,
    job: GenerationJob,
    system: str,
    user_msg: str,
    parse: Callable[[str], dict],
) -> tuple[dict | None, str]:
    """Call the LLM up to llm_parse_max_attempts times. Returns (payload, "")
    on success, or (None, last_error) once attempts are exhausted."""
    llm = get_llm()
    last_error = ""
    for attempt in range(1, settings.llm_parse_max_attempts + 1):
        job.attempts = attempt
        db.commit()
        try:
            raw = llm.complete(
                system=system,
                user=user_msg,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
            return parse(raw), ""
        except OutputContractError as exc:
            last_error = str(exc)
            log.warning("job %s attempt %s parse failure: %s", job.id, attempt, exc)
        except Exception as exc:  # noqa: BLE001 — LLM/transport error; retry within budget
            last_error = f"LLM 호출 실패: {exc}"
            log.warning("job %s attempt %s call failure: %s", job.id, attempt, exc)
    return None, last_error or "생성에 실패했습니다."


# --- parsing ----------------------------------------------------------------
def _try_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _load_json(raw: str) -> dict:
    """Parse the LLM output into a dict, tolerating a stray code fence and — for
    chatty models / pasted chat output — surrounding prose around the JSON."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    data = _try_json(text)
    if data is None:
        # Fall back to the outermost {...} block (handles leading/trailing prose).
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            data = _try_json(text[start : end + 1])
    if data is None:
        raise OutputContractError("JSON 파싱 실패")
    if not isinstance(data, dict) or "status" not in data:
        raise OutputContractError("status 필드가 없습니다.")
    return data


def _parse_generation(raw: str) -> dict:
    data = _load_json(raw)
    if data["status"] == "rejected":
        return data
    if data["status"] != "success":
        raise OutputContractError(f"알 수 없는 status: {data['status']}")
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise OutputContractError("sections 배열이 비었습니다.")
    valid = set(SECTION_TYPES)
    for s in sections:
        if not isinstance(s, dict) or s.get("type") not in valid or "markdown" not in s:
            raise OutputContractError(f"섹션 형식 오류: {s if isinstance(s, dict) else type(s)}")
    return data


def _parse_refine(raw: str, expected_type: str) -> dict:
    data = _load_json(raw)
    if data["status"] == "rejected":
        return data
    if data["status"] != "success":
        raise OutputContractError(f"알 수 없는 status: {data['status']}")
    if data.get("type") != expected_type:
        raise OutputContractError(f"섹션 타입 불일치: {data.get('type')} != {expected_type}")
    if not isinstance(data.get("markdown"), str) or not data["markdown"]:
        raise OutputContractError("markdown 값이 비었습니다.")
    return data


# --- persistence ------------------------------------------------------------
def _store_sections(db: Session, project: Project, sections: list[dict]) -> None:
    """Insert each section as a new latest version, demoting the previous one."""
    for s in sections:
        stype = s["type"]
        prev = db.scalar(
            select(Section)
            .where(Section.project_id == project.id, Section.type == stype, Section.is_latest.is_(True))
            .limit(1)
        )
        next_version = (prev.version + 1) if prev else 1
        if prev is not None:
            db.execute(
                update(Section)
                .where(Section.project_id == project.id, Section.type == stype)
                .values(is_latest=False)
            )
        db.add(
            Section(
                project_id=project.id,
                type=stype,
                title=s.get("title", stype),
                markdown=s["markdown"],
                version=next_version,
                is_latest=True,
            )
        )
    db.commit()


def _finish(db: Session, job: GenerationJob, status: str, error: str | None) -> str:
    job.status = status
    job.error_message = error
    job.finished_at = datetime.now(timezone.utc)
    # Usage accounting for billing/quota (design §db_schema: usage_logs).
    db.add(
        UsageLog(
            user_id=job.user_id,
            job_id=job.id,
            kind=job.kind,
            status=status,
            prompt_version=job.prompt_version,
        )
    )
    db.commit()
    _emit(job, status, error=error)  # terminal event closes the SSE stream
    audit.record(
        db,
        actor_user_id=job.user_id,
        action="job.processed",
        target_type="job",
        target_id=job.id,
        detail={
            "kind": job.kind,
            "status": status,
            "promptVersion": job.prompt_version,
            "attempts": job.attempts,
        },
    )
    return status
