"""
SystemdManager — Linux systemd service management via systemctl.

Extracted from api/autostart.py and api/update.py so those modules
no longer contain platform-specific subprocess calls directly.
"""

from __future__ import annotations

import subprocess
import threading

from app.platform.base.service_mgr import AbstractServiceManager

SERVICE = "anomalynet"
SERVICE_FILE = "/etc/systemd/system/anomalynet.service"


def _systemctl(*args: str, timeout: int = 5) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["systemctl", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return -1, "systemctl not found"
    except Exception as e:
        return -1, str(e)


class SystemdManager(AbstractServiceManager):
    """Manages the anomalynet systemd service."""

    def get_autostart_status(self) -> tuple[bool, bool]:
        """Return (available, enabled)."""
        code, out = _systemctl("is-enabled", SERVICE)
        if code == -1:
            return False, False
        return True, out.strip() == "enabled"

    def set_autostart(self, enable: bool) -> tuple[bool, str]:
        cmd = "enable" if enable else "disable"
        code, out = _systemctl(cmd, SERVICE)
        if code == -1:
            return False, out
        _, enabled = self.get_autostart_status()
        return True, f"{'enabled' if enabled else 'disabled'}: {out[:200]}"

    def restart_service(self) -> bool:
        def _do() -> None:
            import time
            time.sleep(2)
            subprocess.run(["systemctl", "restart", SERVICE], capture_output=True)

        threading.Thread(target=_do, daemon=True).start()
        return True

    def stop_service(self) -> bool:
        code, _ = _systemctl("stop", SERVICE, timeout=15)
        return code == 0

    def disable_and_stop(self) -> tuple[bool, str]:
        rc1, out1 = _systemctl("stop", SERVICE, timeout=15)
        rc2, out2 = _systemctl("disable", SERVICE, timeout=15)
        ok = rc1 == 0 and rc2 == 0
        return ok, f"stop: {out1} | disable: {out2}"

    def remove_service_file(self) -> tuple[bool, str]:
        from pathlib import Path
        svc = Path(SERVICE_FILE)
        try:
            if svc.exists():
                svc.unlink()
                _systemctl("daemon-reload")
            return True, str(svc)
        except Exception as e:
            return False, str(e)

    def reload_daemon(self) -> bool:
        code, _ = _systemctl("daemon-reload")
        return code == 0
