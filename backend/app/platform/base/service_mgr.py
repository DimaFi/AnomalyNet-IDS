"""
AbstractServiceManager — interface for platform-specific service management.

Implementations:
  platform/linux/service_mgr.py   → SystemdManager
  platform/windows/service_mgr.py → WindowsTaskSchedulerManager
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AbstractServiceManager(ABC):
    """Controls startup, autostart, and restart of the AnomalyNet service."""

    @abstractmethod
    def get_autostart_status(self) -> tuple[bool, bool]:
        """Return (available, enabled).
        available=False means the subsystem (systemd/schtasks) is not present.
        """

    @abstractmethod
    def set_autostart(self, enable: bool) -> tuple[bool, str]:
        """Enable or disable autostart. Return (success, message)."""

    @abstractmethod
    def restart_service(self) -> bool:
        """Schedule a service restart. Return True if accepted."""

    @abstractmethod
    def stop_service(self) -> bool:
        """Stop the service. Return True on success."""

    @abstractmethod
    def disable_and_stop(self) -> tuple[bool, str]:
        """Disable autostart and stop the service. Return (success, detail)."""

    @abstractmethod
    def remove_service_file(self) -> tuple[bool, str]:
        """Remove the service definition file. Return (success, detail)."""

    @abstractmethod
    def reload_daemon(self) -> bool:
        """Reload service manager state (systemctl daemon-reload equivalent)."""


class NullServiceManager(AbstractServiceManager):
    """No-op implementation for platforms where service management is unavailable."""

    def get_autostart_status(self) -> tuple[bool, bool]:
        return False, False

    def set_autostart(self, enable: bool) -> tuple[bool, str]:
        return False, "Service management not available on this platform"

    def restart_service(self) -> bool:
        return False

    def stop_service(self) -> bool:
        return False

    def disable_and_stop(self) -> tuple[bool, str]:
        return False, "Service management not available on this platform"

    def remove_service_file(self) -> tuple[bool, str]:
        return True, "No service file on this platform"

    def reload_daemon(self) -> bool:
        return False
