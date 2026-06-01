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


def _detect_app_root() -> Path:
    # 1. Installer sets ANOMALYNET_APP_ROOT (systemd EnvironmentFile / Windows machine env var)
    env_root = _os.environ.get("ANOMALYNET_APP_ROOT")
    if env_root:
        p = Path(env_root)
        if p.exists():
            return p
    # 2. Auto-detect from this file's location:
    #    update.py lives at <root>/backend/app/api/update.py  →  4 parents = <root>
    detected = Path(__file__).parent.parent.parent.parent
    if (detected / ".git").exists() or (detected / "frontend").exists():
        return detected
    # 3. Installed location fallback
    if _platform_sys.system() == "Windows":
        return Path(r"C:\AnomalyNet\AnomalyNet-gui")
    return Path("/opt/anomalynet/AnomalyNet-gui")


GUI_DIR  = _detect_app_root()
ML_DIR   = GUI_DIR.parent / "AnomalyNet-ml"
DIST_DIR = GUI_DIR / "frontend" / "dist"


from app.core import git_safe as _git_safe


def _run(cmd: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(_git_safe(cmd), cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def _npm_path() -> str | None:
    """Returns path to npm, or None if not installed."""
    return shutil.which("npm")


def _git_available() -> bool:
    return shutil.which("git") is not None


def _is_git_repo(repo_dir: Path) -> bool:
    return (repo_dir / ".git").exists()


def _nearest_tag(repo_dir: Path, ref: str = "HEAD") -> str:
    """Return nearest version tag for ref. Falls back to latest tag by sort (for shallow clones)."""
    r = _run(["git", "describe", "--tags", "--abbrev=0", ref], repo_dir)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    # Shallow clone fallback: list all tags sorted by version
    r2 = _run(["git", "tag", "--sort=-version:refname"], repo_dir)
    if r2.returncode == 0:
        tags = [t.strip() for t in r2.stdout.splitlines() if t.strip()]
        if tags:
            return tags[0]
    return ""


def _git_fetch_with_fallback(repo_dir: Path, fallback_urls: list[str]) -> bool:
    """Try git fetch; if it fails, swap origin to each fallback URL and retry."""
    r = _run(["git", "fetch", "--quiet", "--tags"], repo_dir)
    if r.returncode == 0:
        return True
    for url in fallback_urls:
        _run(["git", "remote", "set-url", "origin", url], repo_dir)
        r = _run(["git", "fetch", "--quiet", "--tags"], repo_dir)
        if r.returncode == 0:
            return True
    return False


def _git_info(repo_dir: Path, fallback_urls: list[str] | None = None) -> dict:
    if not repo_dir.exists():
        return {"available": False, "error": f"{repo_dir} не найден"}
    if not _git_available():
        return {
            "available": False,
            "no_git": True,
            "error": "git не установлен — обновление через UI недоступно. Установите Git и запустите установщик заново.",
        }
    if not _is_git_repo(repo_dir):
        return {
            "available": False,
            "no_git_dir": True,
            "error": "Каталог не является git-репозиторием (установка через ZIP). Используйте кнопку «Переустановить» для обновления.",
        }
    try:
        # IMPORTANT: a failed fetch must NOT be silently reported as "up to date".
        # Without network, origin/main stays stale and HEAD == origin/main, which
        # used to show "Всё актуально" even when newer commits existed on GitHub.
        fetched = _git_fetch_with_fallback(repo_dir, fallback_urls or [])
        current = _run(["git", "rev-parse", "HEAD"], repo_dir).stdout.strip()
        latest  = _run(["git", "rev-parse", "origin/main"], repo_dir).stdout.strip()
        msg     = _run(["git", "log", "--oneline", "-1", "origin/main"], repo_dir).stdout.strip()
        cur_tag = _nearest_tag(repo_dir, "HEAD")
        lat_tag = _nearest_tag(repo_dir, "origin/main")
        result = {
            "current":     cur_tag or current[:8],
            "latest":      lat_tag or latest[:8],
            "has_update":  current != latest,
            "latest_msg":  msg.split(" ", 1)[1] if " " in msg else msg,
            "available":   True,
            "fetch_ok":    fetched,
        }
        if not fetched:
            result["warning"] = (
                "Не удалось связаться с сервером обновлений (нет сети или git "
                "заблокирован). Показано последнее известное состояние — "
                "обновления могут быть, но проверить их не удалось."
            )
        return result
    except Exception as e:
        return {"available": False, "error": str(e)}


def _changed_files_after_pull(repo_dir: Path) -> list[str]:
    r = _run(["git", "diff", "HEAD@{1}", "HEAD", "--name-only"], repo_dir)
    return [f.strip() for f in r.stdout.splitlines() if f.strip()]


GUI_REPO_URLS = [
    "https://github.com/DimaFi/AnomalyNet-IDS.git",
    "https://github.com/DimaFi/AnomalyNet-gui.git",
    "https://gitlab.com/DimaFi1/AnomalyNet-gui.git",
]
ML_REPO_URLS = [
    "https://github.com/DimaFi/AnomalyNet-ml.git",
    "https://gitlab.com/DimaFi1/AnomalyNet-ml.git",
]
GUI_REPO_URL = GUI_REPO_URLS[0]
ML_REPO_URL  = ML_REPO_URLS[0]


def _git_pull_hard(repo_dir: Path, clone_url: str | None = None,
                   fallback_urls: list[str] | None = None) -> tuple[bool, str]:
    """Fetch + reset to origin/main.

    Handles three cases:
    - Directory missing + clone_url → git clone
    - Directory exists, no .git + clone_url → git init + remote add + fetch + reset
    - Directory exists with .git → git fetch + reset --hard origin/main
    """
    if not _git_available():
        return False, "git не установлен — обновление через git невозможно"

    # Case 1: directory does not exist → clone fresh
    if not repo_dir.exists():
        if not clone_url:
            return False, f"{repo_dir} не найден и clone_url не указан"
        r = subprocess.run(
            _git_safe(["git", "clone", "--depth=1", clone_url, str(repo_dir)]),
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            return False, f"clone failed: {r.stderr[:300]}"
        # Fetch tags separately — shallow clone doesn't include them by default
        subprocess.run(
            _git_safe(["git", "fetch", "--tags", "--depth=1"]),
            cwd=str(repo_dir), capture_output=True, timeout=60,
        )
        return True, f"cloned {clone_url}"

    # Case 2: directory exists but no .git (ZIP install) → init + connect + fetch
    if not _is_git_repo(repo_dir):
        if not clone_url:
            return False, "Нет .git-репозитория и clone_url не указан — невозможно обновить"
        cmds = [
            ["git", "init"],
            ["git", "remote", "add", "origin", clone_url],
            ["git", "fetch", "--depth=1", "--tags", "origin", "main"],
            ["git", "reset", "--hard", "FETCH_HEAD"],
        ]
        for cmd in cmds:
            r = _run(cmd, repo_dir, timeout=300)
            if r.returncode != 0:
                return False, f"{' '.join(cmd)} failed: {r.stderr[:300]}"
        return True, f"инициализирован и синхронизирован с {clone_url}"

    # Case 3: normal git repo → fetch + reset (with URL fallback)
    fetched = _git_fetch_with_fallback(repo_dir, fallback_urls or [])
    if not fetched:
        return False, "git fetch failed on all remotes (GitHub + GitLab)"
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
    gui = _git_info(GUI_DIR, fallback_urls=GUI_REPO_URLS[1:])
    ml  = _git_info(ML_DIR,  fallback_urls=ML_REPO_URLS[1:])
    # Surface a fetch failure so the UI doesn't show a misleading "up to date".
    warn = gui.get("warning") or ml.get("warning")
    return {
        "gui": gui,
        "ml":  ml,
        "has_any_update": gui.get("has_update", False) or ml.get("has_update", False),
        "fetch_failed": (gui.get("fetch_ok") is False) or (ml.get("fetch_ok") is False),
        "warning": warn,
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
        ok, out = _git_pull_hard(GUI_DIR, clone_url=GUI_REPO_URL, fallback_urls=GUI_REPO_URLS[1:])
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
        ok, out = _git_pull_hard(ML_DIR, clone_url=ML_REPO_URL, fallback_urls=ML_REPO_URLS[1:])
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


@update_router.post("/stop")
async def stop_service() -> dict:
    """Останавливает сервис полностью — убивает весь дерево процессов uvicorn."""
    import asyncio, os, signal

    async def _exit():
        await asyncio.sleep(1.5)
        ppid = os.getppid()

        if _platform_sys.system() == "Windows":
            # Kill parent process tree (uvicorn reloader + all children)
            if ppid > 1:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(ppid)],
                        capture_output=True, timeout=5,
                    )
                except Exception:
                    pass
        else:
            # Linux: kill entire process group
            try:
                os.killpg(os.getpgid(os.getpid()), signal.SIGTERM)
            except Exception:
                try:
                    os.kill(ppid, signal.SIGTERM)
                except Exception:
                    pass

        # Always exit current process as final fallback
        os._exit(0)

    asyncio.create_task(_exit())
    return {"stopped": True, "message": "Сервис остановится через секунду"}


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
        ok, out = _git_pull_hard(GUI_DIR, clone_url=GUI_REPO_URL, fallback_urls=GUI_REPO_URLS[1:])
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
        ok, out = _git_pull_hard(ML_DIR, clone_url=ML_REPO_URL, fallback_urls=ML_REPO_URLS[1:])
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
