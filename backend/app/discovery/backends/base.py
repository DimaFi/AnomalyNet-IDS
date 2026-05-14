"""Abstract base for ARP discovery backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.discovery.models import DeviceInfo


class ArpBackend(ABC):
    """Single-responsibility: turn a network CIDR or single IP into DeviceInfo objects."""

    @abstractmethod
    def scan_network(self, network: str) -> list[DeviceInfo]:
        """Scan all hosts in *network* (CIDR, e.g. '192.168.1.0/24')."""

    def scan_single(self, ip: str) -> str | None:
        """ARP-lookup a single IP → return MAC string (upper) or None."""
        return None

    @property
    def source_tag(self) -> str:
        """Short identifier logged alongside results."""
        return "unknown"
