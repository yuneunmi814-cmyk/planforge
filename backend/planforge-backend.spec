# PyInstaller spec for the PlanForge desktop sidecar.
#
# Build:  pyinstaller planforge-backend.spec
# Output: dist/planforge-backend  (single self-contained executable)
#
# Bundles the prompts/ folder INTO the binary so the sidecar is fully
# self-contained; run_desktop.configure_env() points PROMPTS_DIR at it.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# spec runs with CWD = backend/ ; prompts live at ../prompts
PROMPTS = (str((Path.cwd() / ".." / "prompts").resolve()), "prompts")

hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("anyio")
    + ["app.main"]
)

a = Analysis(
    ["run_desktop.py"],
    pathex=["."],
    binaries=[],
    datas=[PROMPTS],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],  # keep anthropic in: bundled app uses it when the user sets a key
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="planforge-backend",
    console=True,          # keep stdout/stderr so Tauri can capture logs
    onefile=True,
    upx=False,
    disable_windowed_traceback=False,
)
