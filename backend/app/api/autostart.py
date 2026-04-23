"""
Autostart API — check and toggle systemd service autostart.

GET  /api/autostart        — check if anomalynet.service is enabled
POST /api/autostart        — enable or disable autostart
"""

from __future__ import annotations

import subprocess

from fastapi import APIRouter

autostart_router = APIRouter(prefix="/api/autostart")

SERVICE = "anomalynet"


def _systemctl(*args: str, timeout: int = 5) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["systemctl", *args],
            capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return -1, "systemctl not found"
    except Exception as e:
        return -1, str(e)


def _is_enabled() -> tuple[bool, bool]:
    """Returns (available, enabled)."""
    code, out = _systemctl("is-enabled", SERVICE)
    if code == -1:
        return False, False
    return True, out.strip() == "enabled"


@autostart_router.get("")
def get_autostart() -> dict:
    available, enabled = _is_enabled()
    return {
        "available": available,
        "enabled": enabled,
        "message": ("enabled" if enabled else "disabled") if available else "systemctl unavailable",
    }


@autostart_router.post("")
def set_autostart(body: dict) -> dict:
    enable: bool = bool(body.get("enabled", True))
    cmd = "enable" if enable else "disable"
    code, out = _systemctl(cmd, SERVICE)
    if code == -1:
        return {"available": False, "enabled": False, "message": out}
    _, enabled = _is_enabled()
    return {
        "available": True,
        "enabled": enabled,
        "message": f"Service {'enabled' if enabled else 'disabled'}: {out[:200]}" if out else cmd,
    }
