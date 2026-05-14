"""Windows ARP discovery backend.

Primary: Scapy + Npcap (requires Admin).
Fallback: ``arp -a`` cache parsing (always available, passive/limited).
"""

from __future__ import annotations

import ipaddress
import logging
import re
import subprocess
from datetime import datetime
from typing import Callable

from app.discovery.backends.base import ArpBackend
from app.discovery.models import DeviceInfo

_log = logging.getLogger("app.discovery.windows_arp")

# Injectable hooks for testing (same pattern as firewall.py)
_run_arp_a: Callable[[], tuple[int, str]] = lambda: _default_run_arp_a()
_is_admin_fn: Callable[[], bool] = lambda: _default_is_admin()
_has_npcap_fn: Callable[[], bool] = lambda: _default_has_npcap()


def _default_run_arp_a() -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            timeout=10,
        )
        # Try UTF-8 first, then CP866 (Windows ARP output encoding), then replace
        for enc in ("utf-8", "cp866", "cp1251"):
            try:
                text = result.stdout.decode(enc)
                break
            except Exception:
                continue
        else:
            text = result.stdout.decode(errors="replace")
        return result.returncode, text
    except Exception as exc:
        return -1, str(exc)


def _default_is_admin() -> bool:
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
    except Exception:
        return False


def _default_has_npcap() -> bool:
    try:
        from scapy.arch.windows import get_windows_if_list  # type: ignore
        ifaces = get_windows_if_list()
        return isinstance(ifaces, list) and len(ifaces) > 0
    except Exception:
        return False


# ── ARP -a output parser ──────────────────────────────────────────────────────

def parse_arp_cache(output: str) -> list[tuple[str, str]]:
    """Parse ``arp -a`` output into (ip, mac) pairs.

    Handles Windows format::

        192.168.1.1   aa-bb-cc-dd-ee-ff   dynamic

    and also Linux ``arp -a``::

        ? (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on eth0
    """
    results: list[tuple[str, str]] = []
    # Regex: grab an IPv4 address and a MAC (either aa-bb-cc or aa:bb:cc style)
    pattern = re.compile(
        r'(\d{1,3}(?:\.\d{1,3}){3})'              # IP
        r'.*?'                                      # anything between
        r'([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:]'  # MAC first 3 octets
        r'[0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:]'
        r'[0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})'
    )
    for line in output.splitlines():
        m = pattern.search(line)
        if not m:
            continue
        ip_str = m.group(1)
        mac_raw = m.group(2)
        # Validate IP
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        # Skip multicast, loopback, broadcast
        if ip_obj.is_multicast or ip_obj.is_loopback or str(ip_obj) == "255.255.255.255":
            continue
        # Normalise MAC → AA:BB:CC:DD:EE:FF
        mac_norm = re.sub(r"[-.]", ":", mac_raw).upper()
        # Skip all-zeros or broadcast MACs
        if mac_norm in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
            continue
        results.append((ip_str, mac_norm))
    return results


# ── Backend class ─────────────────────────────────────────────────────────────

class WindowsArpBackend(ArpBackend):
    """Platform-aware ARP scanner for Windows.

    Tries Scapy+Npcap when running as Administrator; falls back to
    ``arp -a`` cache parsing otherwise (or if Npcap is unavailable).
    """

    def __init__(self, interface: str | None = None) -> None:
        self._interface = interface

    @property
    def source_tag(self) -> str:
        admin = _is_admin_fn()
        npcap = _has_npcap_fn()
        return "npcap" if (admin and npcap) else "arp_cache"

    # ── Scapy path ────────────────────────────────────────────────────────────

    def _scan_with_scapy(self, network: str) -> list[DeviceInfo] | None:
        """Returns device list on success, None if Scapy/Npcap unavailable."""
        try:
            from scapy.layers.l2 import ARP, Ether  # type: ignore
            from scapy.sendrecv import srp  # type: ignore
        except ImportError:
            return None

        from app.discovery.classifier import guess_device_type
        from app.discovery.oui import get_oui_lookup
        import socket as _socket

        try:
            oui = get_oui_lookup()
            now = datetime.now()
            pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=network)
            answered, _ = srp(pkt, timeout=3, retry=1, verbose=False)
            devices: list[DeviceInfo] = []
            for _, rcv in answered:
                mac: str = rcv.hwsrc.upper()
                ip: str = rcv.psrc
                vendor = oui.lookup(mac)
                try:
                    hostname = _socket.gethostbyaddr(ip)[0]
                except Exception:
                    hostname = ""
                device_type = guess_device_type(vendor=vendor, hostname=hostname)
                devices.append(DeviceInfo(
                    mac=mac, ip=ip, vendor=vendor, device_type=device_type,
                    hostname=hostname, first_seen=now, last_seen=now, is_online=True,
                ))
            _log.info("[SCAN] Scapy/Npcap: %d devices in %s", len(devices), network)
            return devices
        except Exception as exc:
            _log.warning("[SCAN] Scapy scan failed for %s: %s", network, exc)
            return None

    # ── ARP cache fallback ────────────────────────────────────────────────────

    def _scan_with_arp_cache(self, network: str) -> list[DeviceInfo]:
        """Parse ``arp -a`` and filter to *network*."""
        rc, text = _run_arp_a()
        if rc < 0:
            _log.warning("[SCAN] arp -a failed: %s", text)
            return []

        from app.discovery.classifier import guess_device_type
        from app.discovery.oui import get_oui_lookup

        oui = get_oui_lookup()
        now = datetime.now()

        # Parse target network for filtering
        net_obj: ipaddress.IPv4Network | None = None
        try:
            net_obj = ipaddress.ip_network(network, strict=False)
        except ValueError:
            pass

        pairs = parse_arp_cache(text)
        devices: list[DeviceInfo] = []
        for ip_str, mac in pairs:
            if net_obj is not None:
                try:
                    if ipaddress.ip_address(ip_str) not in net_obj:
                        continue
                except ValueError:
                    continue
            vendor = oui.lookup(mac)
            device_type = guess_device_type(vendor=vendor, hostname="")
            devices.append(DeviceInfo(
                mac=mac, ip=ip_str, vendor=vendor, device_type=device_type,
                hostname="", first_seen=now, last_seen=now, is_online=True,
            ))

        _log.info("[SCAN] arp -a cache: %d devices in %s", len(devices), network)
        return devices

    # ── Public API ────────────────────────────────────────────────────────────

    def scan_network(self, network: str) -> list[DeviceInfo]:
        """Scapy+Npcap if admin, else arp -a cache."""
        if _is_admin_fn() and _has_npcap_fn():
            result = self._scan_with_scapy(network)
            if result is not None:
                return result
            _log.warning("[SCAN] Scapy failed — falling back to arp cache for %s", network)
        return self._scan_with_arp_cache(network)

    def scan_single(self, ip: str) -> str | None:
        """ARP single-IP lookup: Scapy → arp -a fallback."""
        if _is_admin_fn() and _has_npcap_fn():
            try:
                from scapy.layers.l2 import ARP, Ether  # type: ignore
                from scapy.sendrecv import srp  # type: ignore
                pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip)
                answered, _ = srp(pkt, timeout=2, retry=1, verbose=False)
                if answered:
                    return answered[0][1].hwsrc.upper()
            except Exception:
                pass
        # arp -a fallback
        try:
            rc, text = _run_arp_a()
            if rc >= 0:
                pairs = parse_arp_cache(text)
                for found_ip, mac in pairs:
                    if found_ip == ip:
                        return mac
        except Exception:
            pass
        return None
