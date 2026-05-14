"""
WindowsTaskSchedulerManager — Windows autostart via schtasks.

Phase 2.0.0 implementation:
  - Autostart via Task Scheduler (schtasks)
  - Restart via re-exec (Popen + sys.exit)
  - All operations are graceful — no crash if schtasks unavailable or no Admin rights

Phase 2.1 will add proper Windows Service (pywin32 / NSSM) support.
"""

from __future__ import annotations

import subprocess
import sys
import threading

from app.platform.base.service_mgr import AbstractServiceManager

TASK_NAME = "AnomalyNet"


def _schtasks(*args: str, timeout: int = 10) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["schtasks", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return -1, "schtasks not found"
    except Exception as e:
        return -1, str(e)


class WindowsTaskSchedulerManager(AbstractServiceManager):
    """
    Manages AnomalyNet autostart via Windows Task Scheduler.

    Autostart = scheduled task that runs on user logon at highest privilege.
    Restart = spawn new process + exit current one (portable mode behaviour).
    """

    def get_autostart_status(self) -> tuple[bool, bool]:
        """Return (available, enabled).
        'enabled' = task exists in Task Scheduler.
        """
        code, out = _schtasks("/query", "/tn", TASK_NAME, "/fo", "LIST")
        if code == -1:
            return False, False
        # Task exists = code 0; task not found = non-zero
        return True, code == 0

    def set_autostart(self, enable: bool) -> tuple[bool, str]:
        if enable:
            exe = sys.executable
            # Use the full exe path for the scheduled task
            code, out = _schtasks(
                "/create",
                "/tn", TASK_NAME,
                "/tr", f'"{exe}"',
                "/sc", "onlogon",
                "/rl", "highest",
                "/f",   # overwrite if exists
            )
        else:
            code, out = _schtasks("/delete", "/tn", TASK_NAME, "/f")
        return code == 0, out[:300] if out else ("enabled" if enable else "disabled")

    def restart_service(self) -> bool:
        """Re-launch the application as a new process and exit the current one."""
        def _do() -> None:
            import time
            time.sleep(2)
            try:
                CREATE_NEW_CONSOLE = 0x00000010
                flags = CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                subprocess.Popen(
                    [sys.executable] + sys.argv,
                    creationflags=flags,
                    close_fds=True,
                )
                sys.exit(0)
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()
        return True

    def stop_service(self) -> bool:
        # In portable mode there is no separate service process to stop
        return True

    def disable_and_stop(self) -> tuple[bool, str]:
        code, out = _schtasks("/delete", "/tn", TASK_NAME, "/f")
        # code 1 = task not found = acceptable
        ok = code in (0, 1)
        return ok, out[:200] if out else "Task Scheduler entry removed"

    def remove_service_file(self) -> tuple[bool, str]:
        return True, "No service file in Windows portable mode"

    def reload_daemon(self) -> bool:
        return True   # no-op on Windows
