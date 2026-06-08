"""Runtime settings API — the in-app settings screen (LLM engine choice).

Default engine is local Ollama (no key); the user can switch to Anthropic and
paste their own key. The key is stored locally (~/.planforge/config.json) and is
never returned in full — only a masked hint.

Also drives Ollama onboarding: detect install/run state, open the download page,
and pull a model with streamed progress — so a fresh user can get to a working
local engine without leaving the app."""

import shutil

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.security import get_current_user
from app.models import User
from app.schemas import OllamaPullReq, SettingsRes, SettingsUpdateReq
from app.services import appconfig

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"


def _mask(key: str) -> str:
    if not key:
        return ""
    return "••••" + key[-4:] if len(key) >= 4 else "••••"


def _to_res(cfg: dict) -> SettingsRes:
    key = cfg.get("anthropicApiKey") or ""
    return SettingsRes(
        llmProvider=cfg["llmProvider"],
        ollamaBaseUrl=cfg["ollamaBaseUrl"],
        ollamaModel=cfg["ollamaModel"],
        anthropicModel=cfg["anthropicModel"],
        hasAnthropicKey=bool(key),
        anthropicKeyMasked=_mask(key),
    )


@router.get("", response_model=SettingsRes)
def get_settings_(user: User = Depends(get_current_user)) -> SettingsRes:
    return _to_res(appconfig.get_config())


@router.put("", response_model=SettingsRes)
def update_settings(
    body: SettingsUpdateReq,
    user: User = Depends(get_current_user),
) -> SettingsRes:
    # exclude_unset so omitted fields aren't overwritten; empty string clears.
    cfg = appconfig.update_config(body.model_dump(exclude_unset=True))
    return _to_res(cfg)


def _ollama_base() -> str:
    return appconfig.get_config()["ollamaBaseUrl"].rstrip("/")


@router.get("/ollama/models")
def list_ollama_models(user: User = Depends(get_current_user)) -> dict:
    """Best-effort: list models installed in the user's local Ollama so the UI
    can offer a picker. Returns an empty list if Ollama isn't running."""
    import httpx

    try:
        resp = httpx.get(f"{_ollama_base()}/api/tags", timeout=3)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return {"available": True, "models": models}
    except Exception:  # noqa: BLE001 — Ollama may simply not be installed/running
        return {"available": False, "models": []}


@router.get("/ollama/status")
def ollama_status(user: User = Depends(get_current_user)) -> dict:
    """Onboarding state machine input:
    - installed: the `ollama` binary is on PATH
    - running:   the local server answers
    - models:    installed model names
    The UI uses this to show "install" vs "start" vs "pull model" vs "ready"."""
    import httpx

    installed = shutil.which("ollama") is not None
    running, version, models = False, None, []
    try:
        ver = httpx.get(f"{_ollama_base()}/api/version", timeout=3)
        ver.raise_for_status()
        running = True
        version = ver.json().get("version")
        tags = httpx.get(f"{_ollama_base()}/api/tags", timeout=3)
        if tags.status_code == 200:
            models = [m["name"] for m in tags.json().get("models", [])]
    except Exception:  # noqa: BLE001
        pass
    return {
        "installed": installed or running,  # running implies installed
        "running": running,
        "version": version,
        "models": models,
        "downloadUrl": OLLAMA_DOWNLOAD_URL,
    }


@router.post("/ollama/open-download")
def open_ollama_download(user: User = Depends(get_current_user)) -> dict:
    """Open the Ollama download page in the user's default browser. The sidecar
    runs locally, so opening the browser here targets the user's machine."""
    import webbrowser

    opened = webbrowser.open(OLLAMA_DOWNLOAD_URL)
    return {"opened": bool(opened), "url": OLLAMA_DOWNLOAD_URL}


@router.post("/ollama/pull")
def pull_ollama_model(
    body: OllamaPullReq,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Pull a model into the local Ollama, streaming progress as NDJSON.

    Proxies Ollama's /api/pull line-by-line so the UI can render a progress bar.
    Requires Ollama to be running (otherwise 409)."""
    import httpx

    model = body.model or appconfig.get_config()["ollamaModel"]

    # Fail fast with a clear error if the server isn't up.
    try:
        httpx.get(f"{_ollama_base()}/api/version", timeout=3).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ollama_not_running") from exc

    def _stream():
        with httpx.stream(
            "POST",
            f"{_ollama_base()}/api/pull",
            json={"model": model, "stream": True},
            timeout=None,
        ) as resp:
            for line in resp.iter_lines():
                if line:
                    yield line + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
