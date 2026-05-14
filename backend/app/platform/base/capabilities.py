"""
PlatformCapabilities — dataclass describing what is available on the current platform.

Used by:
  - GET /api/capabilities  (backend endpoint)
  - frontend to hide/show features that aren't available
  - platform/__init__.py factories to choose correct backends
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlatformCapabilities:
    # ── Identity ──────────────────────────────────────────────────────────────
    platform: str = "unknown"          # "linux" | "windows" | "darwin" | "mock"

    # ── Packet capture ────────────────────────────────────────────────────────
    packet_capture: bool = False       # live capture possible
    raw_capture: bool = False          # BPF / raw sockets available
    tls_inspection: bool = False       # TLS ClientHello parsing via capture
    dns_capture: bool = False          # DNS from captured packets
    quic_capture: bool = False         # QUIC/JA4Q (future)
    wifi_capture: bool = False         # Wi-Fi monitor mode
    loopback_capture: bool = False     # loopback interface capture

    # ── Firewall / blocking ───────────────────────────────────────────────────
    firewall_blocking: bool = False    # active IP blocking
    firewall_gateway_mode: bool = False  # FORWARD chain / routing mode
    firewall_rollback: bool = False    # snapshot/restore support

    # ── Service management ────────────────────────────────────────────────────
    autostart_available: bool = False  # systemd / Task Scheduler
    service_restart: bool = False      # can restart self
    self_update: bool = False          # git pull + rebuild

    # ── Elevation ─────────────────────────────────────────────────────────────
    requires_elevation: bool = False   # root / Admin needed for full features
    current_elevated: bool = False     # running as root / Admin right now

    # ── Discovery ─────────────────────────────────────────────────────────────
    arp_scan: bool = False             # ARP device discovery available

    # ── Backend identifiers ───────────────────────────────────────────────────
    capture_backend: str = "mock"      # "scapy_linux" | "npcap" | "windivert" | "mock"
    firewall_backend: str = "mock"     # "iptables" | "netsh" | "mock"
    service_backend: str = "none"      # "systemd" | "task_scheduler" | "none"

    # ── Warnings / hints for UI ───────────────────────────────────────────────
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
