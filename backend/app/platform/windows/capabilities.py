"""
Windows platform capabilities detection.

Phase 2: passive capture via Npcap + Scapy is implemented (WindowsNpcapCapture).
Blocking via netsh is not yet implemented (Phase 3).

Returns honest capabilities — nothing is falsely claimed as available.
"""

from __future__ import annotations

import shutil

from app.platform.base.capabilities import PlatformCapabilities


def _is_admin() -> bool:
    """Check if running as Administrator."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
    except Exception:
        return False


def _has_npcap() -> bool:
    """Check Npcap is installed and Scapy can enumerate Windows interfaces."""
    try:
        from scapy.arch.windows import get_windows_if_list  # type: ignore[import]
        ifaces = get_windows_if_list()
        return isinstance(ifaces, list) and len(ifaces) > 0
    except Exception:
        return False


def _has_schtasks() -> bool:
    return shutil.which("schtasks") is not None


def _has_scapy() -> bool:
    try:
        import scapy  # noqa: F401
        return True
    except ImportError:
        return False


def windows_capabilities() -> PlatformCapabilities:
    admin = _is_admin()
    npcap = _has_npcap()
    schtasks = _has_schtasks()
    scapy = _has_scapy()

    capture_ready = admin and npcap and scapy

    warnings: list[str] = []
    if not admin:
        warnings.append(
            "Running without Administrator rights — packet capture and firewall blocking "
            "require elevation. Restart as Administrator."
        )
    if not npcap:
        warnings.append(
            "Npcap not detected — live packet capture unavailable. "
            "Install Npcap from https://npcap.com/"
        )
    if not scapy and (admin and npcap):
        warnings.append("scapy not installed — run: pip install scapy")
    if admin and not npcap:
        warnings.append(
            "Active ARP scan unavailable — Npcap not found. "
            "ARP cache fallback will be used for device discovery."
        )

    return PlatformCapabilities(
        platform="windows",
        # Capture — Phase 2 (implemented)
        packet_capture=capture_ready,
        raw_capture=admin and npcap,
        tls_inspection=capture_ready,
        dns_capture=capture_ready,
        quic_capture=False,
        wifi_capture=False,
        loopback_capture=False,
        # Firewall — Phase 3 (implemented via netsh, requires admin)
        firewall_blocking=admin,
        firewall_gateway_mode=False,  # WinDivert needed — Phase 2.1
        firewall_rollback=admin,      # snapshot/restore via netsh advfirewall export/import
        # Service
        autostart_available=schtasks,
        service_restart=True,
        self_update=True,
        # Elevation
        requires_elevation=True,
        current_elevated=admin,
        # Discovery
        arp_scan=capture_ready,
        # Backends
        capture_backend="npcap" if capture_ready else "mock",
        firewall_backend="netsh" if admin else "mock",
        service_backend="task_scheduler" if schtasks else "none",
        warnings=warnings,
    )
