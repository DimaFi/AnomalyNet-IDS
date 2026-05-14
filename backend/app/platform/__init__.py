"""
platform — cross-platform factory module.

Provides:
  get_capabilities()       → PlatformCapabilities
  get_service_manager()    → AbstractServiceManager
  get_firewall(mode)       → BaseFirewall

Usage:
    from app.platform import get_capabilities, get_service_manager, get_firewall
"""

from __future__ import annotations

import platform as _platform

from app.platform.base.capabilities import PlatformCapabilities
from app.platform.base.service_mgr import AbstractServiceManager, NullServiceManager
from app.security.blocker import BaseFirewall


# ── Capabilities ──────────────────────────────────────────────────────────────

def get_capabilities() -> PlatformCapabilities:
    """Return runtime capabilities for the current platform."""
    system = _platform.system().lower()
    if system == "linux":
        from app.platform.linux.capabilities import linux_capabilities
        return linux_capabilities()
    elif system == "windows":
        from app.platform.windows.capabilities import windows_capabilities
        return windows_capabilities()
    else:
        # macOS / unknown — return safe defaults (mock-like)
        return PlatformCapabilities(
            platform=system or "unknown",
            self_update=True,
            service_backend="none",
            capture_backend="mock",
            firewall_backend="mock",
            warnings=[f"Platform '{system}' is not fully supported — running in mock mode."],
        )


# ── Service manager ───────────────────────────────────────────────────────────

def get_service_manager() -> AbstractServiceManager:
    """Return the appropriate service manager for the current platform."""
    system = _platform.system().lower()
    if system == "linux":
        from app.platform.linux.service_mgr import SystemdManager
        return SystemdManager()
    elif system == "windows":
        from app.platform.windows.service_mgr import WindowsTaskSchedulerManager
        return WindowsTaskSchedulerManager()
    else:
        return NullServiceManager()


# ── Firewall ──────────────────────────────────────────────────────────────────

def get_firewall(mode: str = "pc") -> BaseFirewall:
    """
    Return the appropriate firewall backend for the current platform.

    Linux + iptables available → LinuxFirewall
    Windows (Phase 2.0.0)     → MockFirewall (Phase 3: → WindowsNetshFirewall)
    Other                     → MockFirewall

    Note: existing code can still use app.security.blocker.create_firewall()
    directly — it delegates here internally now.
    """
    system = _platform.system().lower()
    if system == "linux":
        from app.platform.linux.capabilities import _has_iptables, _is_root
        if _is_root() and _has_iptables():
            from app.security.blocker import LinuxFirewall
            return LinuxFirewall(blocking_mode=mode)
        from app.security.blocker import MockFirewall
        return MockFirewall(blocking_mode=mode)
    elif system == "windows":
        from app.platform.windows.firewall import create_windows_firewall
        return create_windows_firewall(mode)
    else:
        from app.security.blocker import MockFirewall
        return MockFirewall(blocking_mode=mode)
