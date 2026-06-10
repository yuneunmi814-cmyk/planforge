"""Manual handoff: bring your own ChatGPT / Claude / Gemini (no API key).

Consumer chat subscriptions don't expose a programmatic API, so instead of
calling a model we hand the user the exact prompt to paste into their own chat,
then parse the response they paste back. The system prompt and output contract
are unchanged from the automated path — we just reuse the prompt loader and the
worker's output-contract parser. Free, uses the user's existing subscription,
and stays within every provider's terms."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_approved_user
from app.models import SECTION_TYPES, Project, User
from app.schemas import (
    ManualImportReq,
    ManualImportRes,
    ManualPromptReq,
    ManualPromptRes,
    OpenChatReq,
)
from app.services import audit, prompts
from app.worker.processor import OutputContractError, _parse_generation, _store_sections

router = APIRouter(prefix="/api/v1/manual", tags=["manual"])

# Each provider's "new chat" page. Opened in the user's real browser (where they
# are already logged in), so their subscription does the work.
_CHAT_URLS = {
    "chatgpt": "https://chatgpt.com/",
    "claude": "https://claude.ai/new",
    "gemini": "https://gemini.google.com/app",
}


@router.post("/prompt", response_model=ManualPromptRes)
def manual_prompt(
    body: ManualPromptReq,
    user: User = Depends(get_approved_user),
) -> ManualPromptRes:
    """Assemble the full prompt to paste into a chat (system prompt + input
    contract). No project is created and no model is called."""
    system, version = prompts.generation_system_prompt()
    user_msg = prompts.build_generation_input(
        idea=body.idea,
        frontend=body.frontend,
        backend=body.backend,
        db=body.db,
        auth=body.auth,
    )
    return ManualPromptRes(prompt=f"{system}\n\n{user_msg}", promptVersion=version)


@router.post("/import", response_model=ManualImportRes)
def manual_import(
    body: ManualImportReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_approved_user),
) -> ManualImportRes:
    """Parse a pasted chat response (the output-contract JSON) into a project.

    Reuses the same parser as the automated worker, so a rejected/invalid output
    is handled identically. On success a project + its sections are created and
    the project id is returned — the client then renders it like any other."""
    try:
        payload = _parse_generation(body.text)
    except OutputContractError as exc:
        # The paste wasn't valid contract JSON — surface a clear, actionable 422.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"manual_parse_failed: {exc}",
        ) from exc

    if payload.get("status") == "rejected":
        return ManualImportRes(status="rejected", reason=str(payload.get("reason", "거부됨"))[:500])

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

    _store_sections(db, project, payload["sections"])
    project.assumed_stack = json.dumps(payload.get("assumed_stack"), ensure_ascii=False)
    db.commit()

    audit.record(
        db,
        actor_user_id=user.id,
        action="project.manual_import",
        target_type="project",
        target_id=project.id,
        detail={"sections": len(payload["sections"])},
    )
    return ManualImportRes(status="success", projectId=project.id)


@router.post("/open-chat")
def open_chat(body: OpenChatReq, user: User = Depends(get_approved_user)) -> dict:
    """Open the chosen provider's chat in the user's default browser. The sidecar
    runs locally, so this targets the user's machine (same pattern as the Ollama
    download link)."""
    import webbrowser

    url = _CHAT_URLS[body.provider]
    return {"opened": bool(webbrowser.open(url)), "url": url}
