"""
Update API — git pull for GUI and ML repos, frontend rebuild, optional service restart.

GET  /api/update/check  — fetch latest commits, compare with current
POST /api/update/apply  — pull both repos, rebuild dist, restart if backend changed
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

from fastapi import APIRouter

update_router = APIRouter(prefix="/api/update")

GUI_DIR  = Path("/opt/anomalynet")
ML_DIR   = Path("/opt/anomalynet-ml")
DIST_DIR = GUI_DIR / "frontend" / "dist"


def _run(cmd: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def _npm_path() -> str:
    p = shutil.which("npm")
    return p if p else "/usr/bin/npm"


def _git_info(repo_dir: Path) -> dict:
    if not repo_dir.exists():
        return {"available": False, "error": f"{repo_dir} не найден"}
    try:
        _run(["git", "fetch", "--quiet"], repo_dir)
        current = _run(["git", "rev-parse", "HEAD"], repo_dir).stdout.strip()
        latest  = _run(["git", "rev-parse", "origin/main"], repo_dir).stdout.strip()
        msg     = _run(["git", "log", "--oneline", "-1", "origin/main"], repo_dir).stdout.strip()
        # Nearest tag (e.g. v1.0.0), fallback to short hash
        cur_tag = _run(["git", "describe", "--tags", "--abbrev=0", "HEAD"], repo_dir).stdout.strip()
        lat_tag = _run(["git", "describe", "--tags", "--abbrev=0", "origin/main"], repo_dir).stdout.strip()
        return {
            "current":     cur_tag or current[:8],
            "latest":      lat_tag or latest[:8],
            "has_update":  current != latest,
            "latest_msg":  msg.split(" ", 1)[1] if " " in msg else msg,
            "available":   True,
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


def _changed_files_after_pull(repo_dir: Path) -> list[str]:
    r = _run(["git", "diff", "HEAD@{1}", "HEAD", "--name-only"], repo_dir)
    return [f.strip() for f in r.stdout.splitlines() if f.strip()]


def _git_pull_hard(repo_dir: Path) -> tuple[bool, str]:
    """Fetch + reset to origin/main, handles modified/untracked files."""
    r1 = _run(["git", "fetch", "--quiet"], repo_dir)
    if r1.returncode != 0:
        return False, r1.stderr[:200]
    r2 = _run(["git", "reset", "--hard", "origin/main"], repo_dir)
    return r2.returncode == 0, (r2.stdout + r2.stderr).strip()[-200:]


def _rebuild_dist() -> tuple[bool, str]:
    npm = _npm_path()
    frontend_dir = GUI_DIR / "frontend"
    r = subprocess.run(
        [npm, "run", "build"],
        cwd=str(frontend_dir),
        capture_output=True, text=True, timeout=180,
        env={**__import__("os").environ, "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/lib/nodejs/bin"}
    )
    return r.returncode == 0, (r.stdout + r.stderr)[-600:]


def _schedule_restart() -> None:
    def _do():
        import time
        time.sleep(2)
        subprocess.run(["systemctl", "restart", "anomalynet"], capture_output=True)
    threading.Thread(target=_do, daemon=True).start()


@update_router.get("/check")
def check_updates() -> dict:
    gui = _git_info(GUI_DIR)
    ml  = _git_info(ML_DIR)
    return {
        "gui": gui,
        "ml":  ml,
        "has_any_update": gui.get("has_update", False) or ml.get("has_update", False),
    }


@update_router.post("/apply")
def apply_updates() -> dict:
    result: dict = {
        "gui": {}, "ml": {},
        "dist_rebuilt": False,
        "restart_scheduled": False,
        "message": "",
        "errors": [],
    }

    # Pull GUI repo
    gui_changed: list[str] = []
    try:
        ok, out = _git_pull_hard(GUI_DIR)
        result["gui"]["ok"]     = ok
        result["gui"]["output"] = out or "Already up to date"
        gui_changed = _changed_files_after_pull(GUI_DIR)
        result["gui"]["changed_files"] = gui_changed
    except Exception as e:
        result["gui"]["ok"] = False
        result["errors"].append(f"GUI pull: {e}")

    backend_changed  = any(f.startswith("backend/")  for f in gui_changed)
    frontend_changed = any(f.startswith("frontend/src") or f.startswith("frontend/public") for f in gui_changed)

    # Pull ML repo
    try:
        ok, out = _git_pull_hard(ML_DIR)
        result["ml"]["ok"]     = ok
        result["ml"]["output"] = out or "Already up to date"
    except Exception as e:
        result["ml"]["ok"] = False
        result["errors"].append(f"ML pull: {e}")

    # Rebuild frontend if anything changed or dist exists
    if frontend_changed or DIST_DIR.exists():
        ok, log = _rebuild_dist()
        result["dist_rebuilt"] = ok
        result["dist_log"]     = log
        if not ok:
            result["errors"].append("npm build failed — see dist_log")

    # Restart if backend changed
    if backend_changed:
        _schedule_restart()
        result["restart_scheduled"] = True
        result["message"] = "Бэкенд обновлён — сервис перезапустится через ~2 сек"
    else:
        result["message"] = "Обновление применено без перезапуска сервиса"

    return result
