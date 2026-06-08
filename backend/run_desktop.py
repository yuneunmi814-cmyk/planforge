"""Desktop sidecar entrypoint for PlanForge.

Tauri spawns this as a child process (see desktop-app/src-tauri/src/lib.rs).
It runs the FastAPI app locally with sensible self-contained defaults so the
bundled app works with zero setup:

  - INLINE_DISPATCH=true  → generation runs in-process (no Redis/worker).
  - SQLite DB + event/rate state under the user's home (~/.planforge), which is
    writable even when the app bundle itself is read-only.
  - When frozen by PyInstaller, the prompts/ folder is bundled inside the binary
    (sys._MEIPASS) and PROMPTS_DIR is pointed there.

The frontend talks to it over HTTP on 127.0.0.1:PLANFORGE_PORT (default 8000).
Build it for distribution with PyInstaller — see backend/planforge-backend.spec.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """A per-user, writable directory for the local DB and state."""
    base = Path(os.environ.get("PLANFORGE_DATA_DIR", Path.home() / ".planforge"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def configure_env() -> int:
    """Populate env defaults for local/bundled run. Returns the chosen port.

    Only sets values that aren't already provided, so a power user can override
    anything via real environment variables."""
    data_dir = app_data_dir()

    os.environ.setdefault("PLANFORGE_INLINE_DISPATCH", "true")
    os.environ.setdefault(
        "PLANFORGE_DATABASE_URL", f"sqlite:///{(data_dir / 'planforge.db').as_posix()}"
    )
    # Desktop default = local Ollama (no API key). The user can switch to
    # Anthropic + a key from the in-app settings screen at runtime.
    os.environ.setdefault("PLANFORGE_LLM_PROVIDER", "ollama")

    # When bundled by PyInstaller, ship prompts/ inside the binary and use them.
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        bundled_prompts = Path(bundle_root) / "prompts"
        if bundled_prompts.is_dir():
            os.environ.setdefault("PLANFORGE_PROMPTS_DIR", str(bundled_prompts))

    return int(os.environ.get("PLANFORGE_PORT", "8000"))


def main() -> None:
    port = configure_env()
    # Import AFTER env is configured so Settings picks up our defaults. Pass the
    # app object (not an import string) — more reliable inside a frozen bundle.
    import uvicorn

    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
