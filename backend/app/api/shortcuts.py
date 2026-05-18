"""
Shortcuts API — create desktop / Start Menu shortcuts that launch AnomalyNet.

POST /api/shortcuts/create   { "target": "desktop" | "startmenu" | "applications" }
GET  /api/shortcuts/info     — current app root, launcher path, platform

The shortcut points to launch.bat (Windows) or launch.sh (Linux), NOT to a URL.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter

shortcuts_router = APIRouter(prefix="/api/shortcuts")

# Resolve app root the same way update.py does
def _app_root() -> Path:
    env = os.environ.get("ANOMALYNET_APP_ROOT")
    if env:
        p = Path(env)
        if p.exists():
            return p
    detected = Path(__file__).parent.parent.parent.parent
    if (detected / ".git").exists() or (detected / "frontend").exists():
        return detected
    if platform.system() == "Windows":
        return Path(r"C:\AnomalyNet\AnomalyNet-gui")
    return Path("/opt/anomalynet/AnomalyNet-gui")


def _create_windows_lnk(dest: Path, target: Path, work_dir: Path, description: str) -> tuple[bool, str]:
    """Create a .lnk shortcut via PowerShell WScript.Shell COM object."""
    icon_path = target  # use launcher bat as icon source; installer may add .ico later
    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('{dest}')
$sc.TargetPath  = '{target}'
$sc.WorkingDirectory = '{work_dir}'
$sc.Description = '{description}'
$sc.Save()
"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return True, str(dest)
        return False, r.stderr[:300]
    except Exception as e:
        return False, str(e)


def _create_desktop_file(dest: Path, launcher: Path, app_root: Path) -> tuple[bool, str]:
    """Write an XDG .desktop file for Linux / freedesktop."""
    content = f"""[Desktop Entry]
Name=AnomalyNet IDS
Comment=Network intrusion detection system
Exec=bash {launcher}
Path={app_root}
Icon=network-wired
Terminal=false
Type=Application
Categories=Network;Security;
StartupNotify=true
"""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        dest.chmod(0o755)
        return True, str(dest)
    except Exception as e:
        return False, str(e)


@shortcuts_router.get("/info")
def shortcut_info() -> dict:
    root = _app_root()
    sys = platform.system()
    launcher = root / ("launch.bat" if sys == "Windows" else "launch.sh")
    return {
        "platform": sys,
        "app_root": str(root),
        "launcher_exists": launcher.exists(),
        "launcher_path": str(launcher),
    }


@shortcuts_router.post("/create")
def create_shortcut(body: dict) -> dict:
    target_loc: str = body.get("target", "desktop")
    root = _app_root()
    sys_name = platform.system()

    if sys_name == "Windows":
        launcher = root / "launch.bat"
        if not launcher.exists():
            return {"ok": False, "error": f"Launcher не найден: {launcher}"}

        name = "AnomalyNet IDS.lnk"

        if target_loc == "desktop":
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
                desk = winreg.QueryValueEx(key, "Desktop")[0]
                winreg.CloseKey(key)
            except Exception:
                desk = Path.home() / "Desktop"
            dest = Path(desk) / name
        elif target_loc == "startmenu":
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
                programs = winreg.QueryValueEx(key, "Programs")[0]
                winreg.CloseKey(key)
            except Exception:
                programs = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            dest_dir = Path(programs) / "AnomalyNet"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
        else:
            return {"ok": False, "error": f"Unknown target: {target_loc}"}

        ok, detail = _create_windows_lnk(dest, launcher, root, "AnomalyNet IDS — запустить сервер и открыть интерфейс")
        return {"ok": ok, "path": detail if ok else None, "error": None if ok else detail}

    elif sys_name == "Linux":
        launcher = root / "launch.sh"
        if not launcher.exists():
            return {"ok": False, "error": f"Launcher не найден: {launcher}"}
        launcher.chmod(0o755)

        if target_loc in ("desktop", "applications"):
            if target_loc == "desktop":
                dest = Path.home() / "Desktop" / "anomalynet.desktop"
            else:
                dest = Path.home() / ".local" / "share" / "applications" / "anomalynet.desktop"
            ok, detail = _create_desktop_file(dest, launcher, root)
            # Refresh desktop database
            if ok:
                try:
                    subprocess.run(["update-desktop-database",
                                    str(Path.home() / ".local" / "share" / "applications")],
                                   capture_output=True, timeout=5)
                except Exception:
                    pass
            return {"ok": ok, "path": detail if ok else None, "error": None if ok else detail}
        else:
            return {"ok": False, "error": f"Unknown target: {target_loc}"}
    else:
        return {"ok": False, "error": f"Платформа {sys_name} не поддерживается для создания ярлыков"}
