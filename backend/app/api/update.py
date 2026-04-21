"""
Update API — git pull for GUI and ML repos, frontend rebuild, optional service restart.

GET  /api/update/check  — fetch latest commits, compare with current
POST /api/update/apply  — pull both repos, rebuild dist, restart if backend changed
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from fastapi import APIRouter

update_router = APIRouter(prefix="/api/update")

GUI_DIR = Path("/opt/anomalynet")
ML_DIR  = Path("/opt/anomalynet-ml")
DIST_DIR = GUI_DIR / "frontend" / "dist"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=60)


def _git_info(repo_dir: Path) -> dict:
    try:
        _run(["git", "fetch", "--quiet"], repo_dir)
        current = _run(["git", "rev-parse", "HEAD"], repo_dir).stdout.strip()
        latest  = _run(["git", "rev-parse", "origin/main"], repo_dir).stdout.strip()
        msg     = _run(["git", "log", "--oneline", "-1", "origin/main"], repo_dir).stdout.strip()
        return {
            "current": current[:8],
            "latest": latest[:8],
            "has_update": current != latest,
            "latest_msg": msg,
            "available": True,
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


def _changed_files_after_pull(repo_dir: Path) -> list[str]:
    r = _run(["git", "diff", "HEAD@{1}", "HEAD", "--name-only"], repo_dir)
    return [f.strip() for f in r.stdout.splitlines() if f.strip()]


def _rebuild_dist() -> tuple[bool, str]:
    frontend_dir = GUI_DIR / "frontend"
    r = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(frontend_dir),
        capture_output=True, text=True, timeout=120
    )
    return r.returncode == 0, (r.stdout + r.stderr)[-400:]


def _schedule_restart() -> None:
    def _do():
        import time
        time.sleep(1.5)
        subprocess.run(["systemctl", "restart", "anomalynet"], capture_output=True)
    threading.Thread(target=_do, daemon=True).start()


@update_router.get("/check")
def check_updates() -> dict:
    gui = _git_info(GUI_DIR)
    ml  = _git_info(ML_DIR)
    return {
        "gui": gui,
        "ml": ml,
        "has_any_update": gui.get("has_update", False) or ml.get("has_update", False),
    }


@update_router.post("/apply")
def apply_updates() -> dict:
    result: dict = {"gui": {}, "ml": {}, "dist_rebuilt": False, "restart_scheduled": False, "errors": []}

    # Pull GUI repo
    try:
        r = _run(["git", "pull"], GUI_DIR)
        result["gui"]["output"] = r.stdout.strip()[-200:] or "Already up to date"
        result["gui"]["ok"] = r.returncode == 0
        gui_changed = _changed_files_after_pull(GUI_DIR)
        result["gui"]["changed_files"] = gui_changed
        backend_changed = any(f.startswith("backend/") for f in gui_changed)
        frontend_changed = any(f.startswith("frontend/src") or f.startswith("frontend/public") for f in gui_changed)
    except Exception as e:
        result["gui"]["ok"] = False
        result["errors"].append(f"GUI pull: {e}")
        backend_changed = False
        frontend_changed = False

    # Pull ML repo
    try:
        r = _run(["git", "pull"], ML_DIR)
        result["ml"]["output"] = r.stdout.strip()[-200:] or "Already up to date"
        result["ml"]["ok"] = r.returncode == 0
    except Exception as e:
        result["ml"]["ok"] = False
        result["errors"].append(f"ML pull: {e}")

    # Rebuild frontend dist if frontend files changed (or always if dist exists)
    if frontend_changed or DIST_DIR.exists():
        ok, log = _rebuild_dist()
        result["dist_rebuilt"] = ok
        result["dist_log"] = log

    # Restart service if backend changed
    if backend_changed:
        _schedule_restart()
        result["restart_scheduled"] = True
        result["message"] = "Бэкенд обновлён — сервис перезапустится через ~2 секунды"
    else:
        result["message"] = "Обновление применено без перезапуска"

    return result
