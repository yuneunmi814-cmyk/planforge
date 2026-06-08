"""Runtime settings API — the in-app settings screen (LLM engine choice).

Default engine is local Ollama (no key); the user can switch to Anthropic and
paste their own key. The key is stored locally (~/.planforge/config.json) and is
never returned in full — only a masked hint."""

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models import User
from app.schemas import SettingsRes, SettingsUpdateReq
from app.services import appconfig

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


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


@router.get("/ollama/models")
def list_ollama_models(user: User = Depends(get_current_user)) -> dict:
    """Best-effort: list models installed in the user's local Ollama so the UI
    can offer a picker. Returns an empty list if Ollama isn't running."""
    import httpx

    cfg = appconfig.get_config()
    try:
        resp = httpx.get(f"{cfg['ollamaBaseUrl'].rstrip('/')}/api/tags", timeout=3)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return {"available": True, "models": models}
    except Exception:  # noqa: BLE001 — Ollama may simply not be installed/running
        return {"available": False, "models": []}
