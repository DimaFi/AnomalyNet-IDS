from __future__ import annotations

import os
import platform
from pathlib import Path

# Allow launcher / PyInstaller bundle to override the root path
_env = os.environ.get("ANOMALYNET_APP_ROOT")
APP_ROOT: Path = Path(_env) if _env else Path(__file__).resolve().parents[2]


def git_safe(cmd: list[str]) -> list[str]:
    """Prefix a git command with `-c safe.directory=*`.

    The repo folder is often owned by a different user than the one running the
    panel (installed as Administrator/root, panel runs as the logged-in user).
    Without this, git aborts EVERY command with 'detected dubious ownership',
    which silently breaks update checks and version detection on both Windows
    and Linux.
    """
    if cmd and cmd[0] == "git":
        return ["git", "-c", "safe.directory=*"] + cmd[1:]
    return cmd


def get_user_data_dir() -> Path:
    """
    Returns a persistent, writable directory for user-specific data
    (settings.json, event history). Survives git pull / app updates.

    Override via ANOMALYNET_DATA_DIR env variable.
    """
    override = os.environ.get("ANOMALYNET_DATA_DIR")
    if override:
        return Path(override)

    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    return base / "anomalynet"
