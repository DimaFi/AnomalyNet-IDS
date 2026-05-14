"""
Linux platform capabilities detection.

Checks what is actually available at runtime:
  - root / CAP_NET_RAW
  - iptables / iptables-save
  - systemctl
  - scapy
"""

from __future__ import annotations

import os
import shutil

from app.platform.base.capabilities import PlatformCapabilities


def get_ip_forward() -> bool:
    """Read IP forwarding state from /proc (Linux only)."""
    try:
        return open("/proc/sys/net/ipv4/ip_forward").read().strip() == "1"
    except Exception:
        return False


def _is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False  # Windows — geteuid() absent


def _has_iptables() -> bool:
    return shutil.which("iptables") is not None and shutil.which("iptables-save") is not None


def _has_systemctl() -> bool:
    return shutil.which("systemctl") is not None


def _has_scapy() -> bool:
    try:
        import scapy  # noqa: F401
        return True
    except ImportError:
        return False


def linux_capabilities() -> PlatformCapabilities:
    root = _is_root()
    iptables = _has_iptables()
    systemctl = _has_systemctl()
    scapy = _has_scapy()

    warnings: list[str] = []
    if not root:
        warnings.append(
            "Running without root/CAP_NET_RAW — packet capture and blocking unavailable. "
            "Start with 'sudo' or grant capabilities."
        )
    if not iptables:
        warnings.append("iptables not found — IP blocking will use in-memory mock only.")
    if not scapy:
        warnings.append("scapy not installed — live packet capture unavailable.")

    return PlatformCapabilities(
        platform="linux",
        # Capture
        packet_capture=root and scapy,
        raw_capture=root,
        tls_inspection=root and scapy,
        dns_capture=root and scapy,
        quic_capture=False,
        wifi_capture=root and scapy,
        loopback_capture=root and scapy,
        # Firewall
        firewall_blocking=root and iptables,
        firewall_gateway_mode=root and iptables,
        firewall_rollback=root and iptables,
        # Service
        autostart_available=systemctl,
        service_restart=systemctl,
        self_update=True,
        # Elevation
        requires_elevation=True,
        current_elevated=root,
        # Discovery
        arp_scan=root and scapy,
        # Backends
        capture_backend="scapy_linux" if (root and scapy) else "mock",
        firewall_backend="iptables" if (root and iptables) else "mock",
        service_backend="systemd" if systemctl else "none",
        warnings=warnings,
    )
