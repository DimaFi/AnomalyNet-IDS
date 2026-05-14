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

import os as _os
import platform as _platform_sys

def _default_app_root() -> str:
    if _platform_sys.system() == "Windows":
        return r"C:\AnomalyNet\AnomalyNet-gui"
    return "/opt/anomalynet/AnomalyNet-gui"

# ANOMALYNET_APP_ROOT is set by the installer (systemd on Linux, machine env var on Windows)
GUI_DIR  = Path(_os.environ.get("ANOMALYNET_APP_ROOT", _default_app_root()))
ML_DIR   = GUI_DIR.parent / "AnomalyNet-ml"
DIST_DIR = GUI_DIR / "frontend" / "dist"


def _run(cmd: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def _npm_path() -> str | None:
    """Returns path to npm, or None if not installed."""
    return shutil.which("npm")


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


ML_REPO_URL = "https://github.com/DimaFi/AnomalyNet-ml.git"


def _git_pull_hard(repo_dir: Path, clone_url: str | None = None) -> tuple[bool, str]:
    """Fetch + reset to origin/main. If repo missing and clone_url given — clones first."""
    if not repo_dir.exists() and clone_url:
        r = subprocess.run(
            ["git", "clone", "--depth=1", clone_url, str(repo_dir)],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            return False, f"clone failed: {r.stderr[:300]}"
        return True, f"cloned {clone_url}"
    r1 = _run(["git", "fetch", "--quiet"], repo_dir)
    if r1.returncode != 0:
        return False, r1.stderr[:200]
    r2 = _run(["git", "reset", "--hard", "origin/main"], repo_dir)
    return r2.returncode == 0, (r2.stdout + r2.stderr).strip()[-200:]


def _rebuild_dist() -> tuple[bool, str]:
    npm = _npm_path()
    if npm is None:
        # npm not available — skip rebuild, use pre-built dist from git
        return True, "npm not found — skipped frontend rebuild (using pre-built dist)"
    frontend_dir = GUI_DIR / "frontend"
    import os as _os
    build_env = dict(_os.environ)
    # Ensure npm's own directory is in PATH (cross-platform, no hardcoded Linux paths)
    from pathlib import Path as _Path
    npm_dir = str(_Path(npm).parent)
    existing_path = build_env.get("PATH", "")
    if npm_dir not in existing_path:
        build_env["PATH"] = npm_dir + _os.pathsep + existing_path
    r = subprocess.run(
        [npm, "run", "build"],
        cwd=str(frontend_dir),
        capture_output=True, text=True, timeout=180,
        env=build_env,
    )
    return r.returncode == 0, (r.stdout + r.stderr)[-600:]


def _schedule_restart() -> None:
    from app.platform import get_service_manager
    mgr = get_service_manager()
    mgr.restart_service()


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

    # Pull ML repo (clone if missing)
    try:
        ok, out = _git_pull_hard(ML_DIR, clone_url=ML_REPO_URL)
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


@update_router.post("/restart")
def restart_service() -> dict:
    """Перезапускает сервис (systemd на Linux, re-exec на Windows)."""
    _schedule_restart()
    return {"message": "Сервис перезапускается...", "restart_scheduled": True}


@update_router.post("/uninstall")
def uninstall(keep_settings: bool = True) -> dict:
    """
    Удаление приложения.

    keep_settings=true  — удаляет код и сервис, но сохраняет config/ и data/.
    keep_settings=false — полное удаление: код + config + data + сервис.
    """
    import os

    result: dict = {
        "steps": [],
        "errors": [],
        "keep_settings": keep_settings,
        "message": "",
    }

    def step(name: str, ok: bool, detail: str = "") -> None:
        result["steps"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            result["errors"].append(f"{name}: {detail}")

    # 1. Stop and disable service (platform-aware)
    try:
        from app.platform import get_service_manager
        svc_mgr = get_service_manager()
        ok, detail = svc_mgr.disable_and_stop()
        step("service stop+disable", ok, detail)
    except Exception as e:
        step("service stop+disable", False, str(e))

    # 2. Remove service file (platform-aware)
    try:
        from app.platform import get_service_manager
        svc_mgr = get_service_manager()
        ok, detail = svc_mgr.remove_service_file()
        step("remove service file", ok, detail)
    except Exception as e:
        step("remove service file", False, str(e))

    # 3. If full wipe — remove config and data
    if not keep_settings:
        for subdir in ("config", "data"):
            target = GUI_DIR / subdir
            try:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                    step(f"remove {subdir}/", True, str(target))
            except Exception as e:
                step(f"remove {subdir}/", False, str(e))

    # 4. Remove app directories (but keep parent /opt/anomalynet if it has other things)
    for repo_dir in [GUI_DIR, ML_DIR]:
        try:
            if repo_dir.exists():
                shutil.rmtree(repo_dir, ignore_errors=True)
                step(f"remove {repo_dir.name}", True, str(repo_dir))
            else:
                step(f"remove {repo_dir.name}", True, "not found — skipped")
        except Exception as e:
            step(f"remove {repo_dir.name}", False, str(e))

    result["message"] = (
        "Приложение удалено. Пользовательские данные сохранены в " + str(GUI_DIR) if keep_settings
        else "Приложение полностью удалено вместе со всеми данными"
    )
    return result


@update_router.post("/reinstall")
def reinstall(wipe_settings: bool = False) -> dict:
    """
    Переустановка: git pull → pip install → [опционально сброс данных] → npm build → restart.

    wipe_settings=false — обновляет код и зависимости, сохраняет все настройки.
    wipe_settings=true  — то же + удаляет config/settings.json и data/ (история, блокировки).
    """
    import os
    import sys

    result: dict = {
        "steps": [],
        "errors": [],
        "wipe_settings": wipe_settings,
        "restart_scheduled": False,
        "message": "",
    }

    def step(name: str, ok: bool, detail: str = "") -> None:
        result["steps"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            result["errors"].append(f"{name}: {detail}")

    # Preserve user config before git reset (git reset --hard would wipe them)
    _cfg_dir = GUI_DIR / "config"
    _saved: dict[str, str | None] = {}
    for _fname in ("settings.json", "models_registry.json", "model_presets.json"):
        _p = _cfg_dir / _fname
        _saved[_fname] = _p.read_text(encoding="utf-8") if _p.exists() else None

    # 1. git pull GUI repo
    try:
        ok, out = _git_pull_hard(GUI_DIR)
        step("git pull GUI", ok, out)
    except Exception as e:
        step("git pull GUI", False, str(e))

    # Restore user config (always — git reset --hard would have overwritten them)
    _cfg_dir.mkdir(parents=True, exist_ok=True)
    for _fname, _content in _saved.items():
        if _content is not None:
            (_cfg_dir / _fname).write_text(_content, encoding="utf-8")

    # 2. git pull / clone ML repo
    try:
        ok, out = _git_pull_hard(ML_DIR, clone_url=ML_REPO_URL)
        step("git pull ML", ok, out)
    except Exception as e:
        step("git pull ML", False, str(e))

    # 3. pip install dependencies
    try:
        req = GUI_DIR / "backend" / "requirements.txt"
        # Prefer the venv pip co-located with sys.executable (works on Linux and Windows)
        _pip_suffix = "pip.exe" if sys.platform == "win32" else "pip"
        _venv_pip = Path(sys.executable).parent / _pip_suffix
        if _venv_pip.exists():
            pip_cmd = [str(_venv_pip), "install", "-q", "-r", str(req)]
        else:
            pip_cmd = [sys.executable, "-m", "pip", "install", "-q", "-r", str(req)]
        r = subprocess.run(pip_cmd, capture_output=True, text=True, timeout=120)
        step("pip install", r.returncode == 0, (r.stdout + r.stderr)[-300:] if r.returncode != 0 else "ok")
    except Exception as e:
        step("pip install", False, str(e))

    # 4. Wipe settings and data (optional)
    if wipe_settings:
        wiped: list[str] = []
        cfg = GUI_DIR / "config" / "settings.json"
        if cfg.exists():
            cfg.unlink()
            wiped.append("config/settings.json")
        data_dir = GUI_DIR / "data"
        if data_dir.exists():
            shutil.rmtree(data_dir, ignore_errors=True)
            wiped.append("data/")
        step("wipe settings+data", True, "Удалено: " + (", ".join(wiped) if wiped else "нечего удалять"))

    # 5. Rebuild frontend
    ok, log = _rebuild_dist()
    step("npm build", ok, log[-300:] if not ok else "ok")

    # 6. Schedule restart
    _schedule_restart()
    result["restart_scheduled"] = True

    has_errors = bool(result["errors"])
    result["message"] = (
        ("Переустановка завершена с ошибками — сервис перезапускается" if has_errors else
         "Переустановка завершена — сервис перезапускается через ~2 сек")
    )
    return result
