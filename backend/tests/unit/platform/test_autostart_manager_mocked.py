"""
Unit tests for service managers with mocked subprocess.

Tests SystemdManager and WindowsTaskSchedulerManager without calling
real systemctl / schtasks — pure logic tests.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestSystemdManager:
    def _manager(self):
        from app.platform.linux.service_mgr import SystemdManager
        return SystemdManager()

    def test_get_autostart_status_enabled(self):
        mgr = self._manager()
        with patch("app.platform.linux.service_mgr._systemctl", return_value=(0, "enabled")):
            available, enabled = mgr.get_autostart_status()
        assert available is True
        assert enabled is True

    def test_get_autostart_status_disabled(self):
        mgr = self._manager()
        with patch("app.platform.linux.service_mgr._systemctl", return_value=(1, "disabled")):
            available, enabled = mgr.get_autostart_status()
        assert available is True
        assert enabled is False

    def test_get_autostart_status_not_available(self):
        mgr = self._manager()
        with patch("app.platform.linux.service_mgr._systemctl", return_value=(-1, "systemctl not found")):
            available, enabled = mgr.get_autostart_status()
        assert available is False
        assert enabled is False

    def test_set_autostart_enable(self):
        mgr = self._manager()
        with patch("app.platform.linux.service_mgr._systemctl") as mock_ctl:
            mock_ctl.side_effect = [
                (0, ""),          # enable command
                (0, "enabled"),   # is-enabled check
            ]
            ok, msg = mgr.set_autostart(True)
        assert ok is True

    def test_set_autostart_failure_returns_false(self):
        mgr = self._manager()
        with patch("app.platform.linux.service_mgr._systemctl", return_value=(-1, "systemctl not found")):
            ok, msg = mgr.set_autostart(True)
        assert ok is False
        assert "not found" in msg

    def test_restart_service_spawns_thread(self):
        mgr = self._manager()
        threads_before = []
        import threading
        threads_before = list(threading.enumerate())
        result = mgr.restart_service()
        assert result is True

    def test_stop_service_calls_systemctl(self):
        mgr = self._manager()
        with patch("app.platform.linux.service_mgr._systemctl", return_value=(0, "")) as mock_ctl:
            ok = mgr.stop_service()
        assert ok is True
        mock_ctl.assert_called_once_with("stop", "anomalynet", timeout=15)

    def test_disable_and_stop_both_called(self):
        mgr = self._manager()
        with patch("app.platform.linux.service_mgr._systemctl", return_value=(0, "")) as mock_ctl:
            ok, detail = mgr.disable_and_stop()
        assert ok is True
        assert mock_ctl.call_count == 2

    def test_reload_daemon(self):
        mgr = self._manager()
        with patch("app.platform.linux.service_mgr._systemctl", return_value=(0, "")) as mock_ctl:
            ok = mgr.reload_daemon()
        assert ok is True
        mock_ctl.assert_called_with("daemon-reload")


class TestWindowsTaskSchedulerManager:
    def _manager(self):
        from app.platform.windows.service_mgr import WindowsTaskSchedulerManager
        return WindowsTaskSchedulerManager()

    def test_get_autostart_status_exists(self):
        mgr = self._manager()
        with patch("app.platform.windows.service_mgr._schtasks", return_value=(0, "Task Name: AnomalyNet")):
            available, enabled = mgr.get_autostart_status()
        assert available is True
        assert enabled is True

    def test_get_autostart_status_not_found(self):
        mgr = self._manager()
        with patch("app.platform.windows.service_mgr._schtasks", return_value=(1, "ERROR: Task does not exist")):
            available, enabled = mgr.get_autostart_status()
        assert available is True
        assert enabled is False

    def test_get_autostart_status_schtasks_missing(self):
        mgr = self._manager()
        with patch("app.platform.windows.service_mgr._schtasks", return_value=(-1, "schtasks not found")):
            available, enabled = mgr.get_autostart_status()
        assert available is False
        assert enabled is False

    def test_set_autostart_enable(self):
        mgr = self._manager()
        with patch("app.platform.windows.service_mgr._schtasks", return_value=(0, "SUCCESS")):
            ok, msg = mgr.set_autostart(True)
        assert ok is True

    def test_set_autostart_disable(self):
        mgr = self._manager()
        with patch("app.platform.windows.service_mgr._schtasks", return_value=(0, "SUCCESS")):
            ok, msg = mgr.set_autostart(False)
        assert ok is True

    def test_disable_and_stop_task_not_found_is_ok(self):
        """Exit code 1 from schtasks /delete means 'task not found' — acceptable."""
        mgr = self._manager()
        with patch("app.platform.windows.service_mgr._schtasks", return_value=(1, "ERROR: task not found")):
            ok, detail = mgr.disable_and_stop()
        assert ok is True  # code 1 is acceptable

    def test_remove_service_file_is_noop(self):
        mgr = self._manager()
        ok, detail = mgr.remove_service_file()
        assert ok is True
        assert "No service file" in detail

    def test_reload_daemon_is_noop(self):
        mgr = self._manager()
        assert mgr.reload_daemon() is True
