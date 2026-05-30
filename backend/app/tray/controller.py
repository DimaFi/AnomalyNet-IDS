"""
PanelController — talk to the AnomalyNet panel over HTTP and manage its process.

The tray app is a separate lightweight process. It controls the panel only
through the local HTTP API (start/stop/restart) plus launching the uvicorn
process directly when the panel is down (no endpoint exists then).

Mirrors the app-root / venv-python detection used by update.py and launch.sh.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import webbrowser
from pathlib import Path

import httpx

_log = logging.getLogger("app.tray.controller")

HOST = "127.0.0.1"
PORT = 8000
BASE = f"http://{HOST}:{PORT}"
PANEL_URL = f"http://localhost:{PORT}"


def detect_app_root() -> Path:
    """Locate the repo root (folder that contains backend/ and launch.*).

    Same strategy as update.py::_detect_app_root() and shortcuts.py::_app_root().
    """
    env_root = os.environ.get("ANOMALYNET_APP_ROOT")
    if env_root:
        p = Path(env_root)
        if p.exists():
            return p
    # tray/controller.py lives at <root>/backend/app/tray/controller.py → 4 parents = <root>
    detected = Path(__file__).resolve().parent.parent.parent.parent
    if (detected / "backend").exists() or (detected / "launch.sh").exists():
        return detected
    if platform.system() == "Windows":
        return Path(r"C:\AnomalyNet\AnomalyNet-gui")
    return Path("/opt/anomalynet/AnomalyNet-gui")


def venv_python(root: Path, windowless: bool = True) -> str:
    """Path to the venv python. Prefers pythonw.exe on Windows (no console)."""
    if platform.system() == "Windows":
        exe = "pythonw.exe" if windowless else "python.exe"
        cand = root / "backend" / ".venv" / "Scripts" / exe
        if cand.exists():
            return str(cand)
        cand = root / "backend" / ".venv" / "Scripts" / "python.exe"
        if cand.exists():
            return str(cand)
    else:
        cand = root / "backend" / ".venv" / "bin" / "python"
        if cand.exists():
            return str(cand)
    # Fallback to whatever interpreter runs the tray
    return sys.executable


class PanelController:
    def __init__(self) -> None:
        self.root = detect_app_root()

    # ── Status ──────────────────────────────────────────────────────────────
    def is_running(self) -> bool:
        try:
            r = httpx.get(f"{BASE}/api/health", timeout=1.5)
            return r.status_code == 200
        except Exception:
            return False

    def metrics(self) -> dict | None:
        """Returns the /api/system/stats payload, or None if unreachable."""
        try:
            r = httpx.get(f"{BASE}/api/system/stats", timeout=2.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    # ── Lifecycle ───────────────────────────────────────────────────────────
    def start(self) -> bool:
        """Launch uvicorn directly (detached, no browser). No-op if already up."""
        if self.is_running():
            return True
        py = venv_python(self.root, windowless=True)
        backend_dir = self.root / "backend"
        cmd = [py, "-m", "uvicorn", "app.main:app", "--host", HOST,
               "--port", str(PORT), "--app-dir", str(backend_dir)]
        try:
            if platform.system() == "Windows":
                CREATE_NO_WINDOW = 0x08000000
                DETACHED_PROCESS = 0x00000008
                subprocess.Popen(
                    cmd, cwd=str(backend_dir),
                    creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                    close_fds=True,
                )
            else:
                logf = open(self.root / "anomalynet.log", "ab")
                subprocess.Popen(
                    cmd, cwd=str(backend_dir),
                    stdout=logf, stderr=logf,
                    start_new_session=True, close_fds=True,
                )
            _log.info("[tray] panel start requested: %s", " ".join(cmd))
            return True
        except Exception as exc:
            _log.error("[tray] panel start failed: %s", exc)
            return False

    def stop(self) -> bool:
        """Ask the panel to shut down its whole process tree."""
        try:
            httpx.post(f"{BASE}/api/update/stop", timeout=3.0)
            return True
        except Exception as exc:
            _log.warning("[tray] stop request error (panel may be down already): %s", exc)
            return False

    def restart(self) -> bool:
        """Restart via API if running, otherwise start fresh."""
        if self.is_running():
            try:
                httpx.post(f"{BASE}/api/update/restart", timeout=3.0)
                return True
            except Exception as exc:
                _log.warning("[tray] restart request error: %s", exc)
                return False
        return self.start()

    # ── Misc ────────────────────────────────────────────────────────────────
    def open_panel(self) -> None:
        try:
            webbrowser.open(PANEL_URL)
        except Exception as exc:
            _log.warning("[tray] open_panel error: %s", exc)
