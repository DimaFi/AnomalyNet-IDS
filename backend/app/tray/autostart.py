"""
Autostart management for the tray app and the panel — two independent entries.

Works whether the panel is running or not (writes OS login entries directly,
not via the panel API). Mirrors what the installers create:

  Windows  HKCU\...\Run :  "AnomalyNet IDS"  -> wscript.exe "<root>\launch.vbs"  (panel)
                           "AnomalyNet Tray" -> wscript.exe "<root>\tray.vbs"    (tray)
  Linux    ~/.config/autostart/ :  anomalynet.desktop       (panel)
                                   anomalynet-tray.desktop  (tray)

Public API: is_enabled(which), enable(which), disable(which)  for which in {"panel","tray"}.
All functions are best-effort and never raise.
"""

from __future__ import annotations

import logging
import platform
from pathlib import Path

_log = logging.getLogger("app.tray.autostart")

_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_WIN_VALUE = {"panel": "AnomalyNet IDS", "tray": "AnomalyNet Tray"}
_WIN_LAUNCHER = {"panel": "launch.vbs", "tray": "tray.vbs"}

_LINUX_DESKTOP = {"panel": "anomalynet.desktop", "tray": "anomalynet-tray.desktop"}
_LINUX_LAUNCHER = {"panel": "launch.sh", "tray": "tray.sh"}
_LINUX_NAME = {"panel": "AnomalyNet IDS", "tray": "AnomalyNet Control"}


def _is_windows() -> bool:
    return platform.system() == "Windows"


# ── Windows (registry) ──────────────────────────────────────────────────────

def _win_is_enabled(which: str) -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
            winreg.QueryValueEx(key, _WIN_VALUE[which])
        return True
    except FileNotFoundError:
        return False
    except Exception as exc:
        _log.debug("[autostart] win read %s: %s", which, exc)
        return False


def _win_set(which: str, root: Path, enable: bool) -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            if enable:
                vbs = root / _WIN_LAUNCHER[which]
                data = f'wscript.exe "{vbs}"'
                winreg.SetValueEx(key, _WIN_VALUE[which], 0, winreg.REG_SZ, data)
            else:
                try:
                    winreg.DeleteValue(key, _WIN_VALUE[which])
                except FileNotFoundError:
                    pass
        return True
    except Exception as exc:
        _log.error("[autostart] win set %s=%s: %s", which, enable, exc)
        return False


# ── Linux (XDG autostart) ───────────────────────────────────────────────────

def _linux_path(which: str) -> Path:
    return Path.home() / ".config" / "autostart" / _LINUX_DESKTOP[which]


def _linux_is_enabled(which: str) -> bool:
    p = _linux_path(which)
    if not p.exists():
        return False
    try:
        # Respect an explicit disable flag if present
        return "X-GNOME-Autostart-enabled=false" not in p.read_text(encoding="utf-8")
    except Exception:
        return True


def _linux_set(which: str, root: Path, enable: bool) -> bool:
    p = _linux_path(which)
    try:
        if enable:
            launcher = root / _LINUX_LAUNCHER[which]
            icon = root / "frontend" / "public" / "logo.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                "[Desktop Entry]\n"
                f"Name={_LINUX_NAME[which]}\n"
                "Type=Application\n"
                f"Exec=bash {launcher}\n"
                f"Path={root}\n"
                f"Icon={icon}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        else:
            p.unlink(missing_ok=True)
        return True
    except Exception as exc:
        _log.error("[autostart] linux set %s=%s: %s", which, enable, exc)
        return False


# ── Public API ──────────────────────────────────────────────────────────────

def is_enabled(which: str) -> bool:
    return _win_is_enabled(which) if _is_windows() else _linux_is_enabled(which)


def enable(which: str, root: Path) -> bool:
    return _win_set(which, root, True) if _is_windows() else _linux_set(which, root, True)


def disable(which: str, root: Path) -> bool:
    return _win_set(which, root, False) if _is_windows() else _linux_set(which, root, False)


def toggle(which: str, root: Path) -> bool:
    """Flip the state; returns the new enabled state."""
    if is_enabled(which):
        disable(which, root)
        return False
    enable(which, root)
    return True
