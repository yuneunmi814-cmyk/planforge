"""Sidecar entrypoint env defaults (desktop packaging)."""

import os

import run_desktop

_KEYS = ["PLANFORGE_INLINE_DISPATCH", "PLANFORGE_DATABASE_URL", "PLANFORGE_PROMPTS_DIR", "PLANFORGE_PORT"]


def test_configure_env_sets_local_defaults(tmp_path, monkeypatch):
    saved = {k: os.environ.get(k) for k in _KEYS}
    for k in _KEYS:
        os.environ.pop(k, None)
    monkeypatch.setenv("PLANFORGE_DATA_DIR", str(tmp_path))
    try:
        port = run_desktop.configure_env()
        assert port == 8000
        assert os.environ["PLANFORGE_INLINE_DISPATCH"] == "true"
        assert os.environ["PLANFORGE_DATABASE_URL"].endswith("planforge.db")
        assert str(tmp_path) in os.environ["PLANFORGE_DATABASE_URL"]
        assert tmp_path.exists()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_configure_env_respects_overrides(tmp_path, monkeypatch):
    saved = {k: os.environ.get(k) for k in _KEYS}
    monkeypatch.setenv("PLANFORGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PLANFORGE_PORT", "9123")
    monkeypatch.setenv("PLANFORGE_INLINE_DISPATCH", "false")
    try:
        port = run_desktop.configure_env()
        assert port == 9123
        assert os.environ["PLANFORGE_INLINE_DISPATCH"] == "false"  # not overwritten
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
