"""
Autostart API — check and toggle service autostart.

GET  /api/autostart   — check if autostart is enabled
POST /api/autostart   — enable or disable autostart

Delegates to platform-specific ServiceManager:
  Linux   → SystemdManager (systemctl enable/disable anomalynet)
  Windows → WindowsTaskSchedulerManager (schtasks)
  Other   → NullServiceManager (always returns available=False)
"""

from __future__ import annotations

from fastapi import APIRouter

autostart_router = APIRouter(prefix="/api/autostart")


def _get_manager():
    from app.platform import get_service_manager
    return get_service_manager()


@autostart_router.get("")
def get_autostart() -> dict:
    mgr = _get_manager()
    available, enabled = mgr.get_autostart_status()
    return {
        "available": available,
        "enabled": enabled,
        "message": ("enabled" if enabled else "disabled") if available else "autostart unavailable on this platform",
    }


@autostart_router.post("")
def set_autostart(body: dict) -> dict:
    enable: bool = bool(body.get("enabled", True))
    mgr = _get_manager()
    ok, msg = mgr.set_autostart(enable)
    if not ok:
        available, _ = mgr.get_autostart_status()
        return {"available": available, "enabled": False, "message": msg}
    _, enabled = mgr.get_autostart_status()
    return {
        "available": True,
        "enabled": enabled,
        "message": msg,
    }
