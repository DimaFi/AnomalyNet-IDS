from __future__ import annotations

import asyncio
import ipaddress
import logging
import platform
import socket
import subprocess
import time
from datetime import datetime
from typing import TYPE_CHECKING

import psutil

from app.discovery.classifier import guess_device_type
from app.discovery.models import DeviceInfo
from app.discovery.oui import get_oui_lookup

if TYPE_CHECKING:
    from app.discovery.tracker import DeviceTracker

logger = logging.getLogger(__name__)


def detect_local_networks(interface: str | None = None) -> list[str]:
    """Return list of CIDR networks for local non-loopback interfaces.

    If *interface* is specified, only that interface is used.
    Falls back to all suitable interfaces if the given one has no IPv4 address.
    """
    addrs = psutil.net_if_addrs()
    candidates: list[str] = []

    iface_names = [interface] if interface else list(addrs.keys())

    for iface in iface_names:
        if iface not in addrs:
            continue
        for addr in addrs[iface]:
            # AF_INET = 2
            if addr.family != 2:
                continue
            ip = addr.address
            netmask = addr.netmask
            if not ip or not netmask:
                continue
            # Skip loopback and link-local
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.is_loopback or ip_obj.is_link_local:
                continue
            try:
                network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
                # Skip tiny or huge networks
                if network.prefixlen < 8 or network.prefixlen > 30:
                    continue
                candidates.append(str(network))
            except ValueError:
                continue

    if not candidates and interface:
        # Fallback: retry without interface filter
        return detect_local_networks(None)

    return candidates

def probe_host(ip: str, ports: list[int] | None = None) -> dict:
    """Ping + port scan a host. Returns reachable, latency_ms, open_ports."""
    t0 = time.monotonic()
    reachable = False
    latency_ms: float | None = None

    # ICMP ping
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", "1000", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=3)
        if result.returncode == 0:
            reachable = True
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
    except Exception:
        pass

    # Port probe (fallback if ping blocked)
    check_ports = ports or [80, 443, 22, 8080, 554, 23, 8443]
    open_ports: list[int] = []
    for port in check_ports:
        try:
            with socket.create_connection((ip, port), timeout=0.5):
                open_ports.append(port)
                if not reachable:
                    reachable = True
                    latency_ms = round((time.monotonic() - t0) * 1000, 1)
        except Exception:
            pass

    return {"reachable": reachable, "latency_ms": latency_ms, "open_ports": open_ports}


def arp_single_ip(ip: str) -> str | None:
    """ARP-lookup a single IP → return MAC or None."""
    try:
        from scapy.layers.l2 import ARP, Ether  # type: ignore
        from scapy.sendrecv import srp  # type: ignore
        pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip)
        answered, _ = srp(pkt, timeout=2, retry=1, verbose=False)
        if answered:
            return answered[0][1].hwsrc.upper()
    except Exception:
        pass
    return None


def _resolve_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def _scan_arp(network: str) -> list[DeviceInfo]:
    try:
        from scapy.layers.l2 import ARP, Ether  # type: ignore
        from scapy.sendrecv import srp  # type: ignore
    except ImportError:
        raise RuntimeError("scapy is not installed — ARP scan unavailable")

    oui = get_oui_lookup()
    devices: list[DeviceInfo] = []
    now = datetime.now()

    pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=network)
    answered, _ = srp(pkt, timeout=3, retry=2, verbose=False)

    for _, rcv in answered:
        mac: str = rcv.hwsrc.upper()
        ip: str = rcv.psrc
        vendor = oui.lookup(mac)
        hostname = _resolve_hostname(ip)
        device_type = guess_device_type(vendor=vendor, hostname=hostname)
        devices.append(DeviceInfo(
            mac=mac, ip=ip, vendor=vendor, device_type=device_type,
            hostname=hostname, first_seen=now, last_seen=now,
            is_online=True,
        ))

    return devices


class NetworkScanner:
    def __init__(self, interface: str | None = None) -> None:
        self._interface = interface  # None = auto-detect

    def _get_networks(self) -> list[str]:
        networks = detect_local_networks(self._interface)
        if networks:
            logger.info("ARP scan targets: %s", networks)
        else:
            logger.warning("No suitable network found for ARP scan")
        return networks

    def scan_once(self) -> list[DeviceInfo]:
        networks = self._get_networks()
        if not networks:
            return []
        all_devices: list[DeviceInfo] = []
        for net in networks:
            try:
                all_devices.extend(_scan_arp(net))
            except Exception as exc:
                logger.warning("ARP scan failed for %s: %s", net, exc)
        return all_devices

    async def start_background_scan(
        self,
        tracker: "DeviceTracker",
        interval: int = 60,
    ) -> None:
        while True:
            try:
                devices = await asyncio.get_event_loop().run_in_executor(None, self.scan_once)
                tracker.merge_scan_results(devices)
                logger.debug("Scan complete: %d devices", len(devices))
            except Exception as exc:
                logger.warning("Network scan failed: %s", exc)
            await asyncio.sleep(interval)
