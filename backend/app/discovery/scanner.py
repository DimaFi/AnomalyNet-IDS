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

from app.discovery.backends.base import ArpBackend
from app.discovery.classifier import guess_device_type
from app.discovery.models import DeviceInfo
from app.discovery.oui import get_oui_lookup

if TYPE_CHECKING:
    from app.discovery.tracker import DeviceTracker

logger = logging.getLogger(__name__)


def _create_arp_backend(interface: str | None = None) -> ArpBackend:
    """Return platform-appropriate ARP discovery backend."""
    if platform.system() == "Windows":
        from app.discovery.backends.windows_arp import WindowsArpBackend
        return WindowsArpBackend(interface=interface)
    from app.discovery.backends.linux_arp import LinuxArpBackend
    return LinuxArpBackend()


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

def _parse_ping_rtt(output: bytes, system: str) -> float | None:
    """Extract RTT from ping stdout. Returns ms or None."""
    import re
    text = output.decode(errors="ignore")
    if system == "windows":
        # "Average = 3ms" or "Minimum = 1ms, Maximum = 5ms, Average = 3ms"
        m = re.search(r"Average\s*=\s*(\d+)ms", text)
        if m:
            return float(m.group(1))
        # fallback: "time=3ms"
        m = re.search(r"time[<=](\d+)ms", text)
        if m:
            return float(m.group(1))
    else:
        # "rtt min/avg/max/mdev = 0.123/0.456/0.789/0.111 ms"
        m = re.search(r"rtt .+ = [\d.]+/([\d.]+)/", text)
        if m:
            return round(float(m.group(1)), 1)
        # "time=0.456 ms"
        m = re.search(r"time=([\d.]+) ms", text)
        if m:
            return round(float(m.group(1)), 1)
    return None


def probe_host(ip: str, ports: list[int] | None = None) -> dict:
    """Ping + port scan a host. Returns reachable, latency_ms, open_ports."""
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
            latency_ms = _parse_ping_rtt(result.stdout, system)
    except Exception:
        pass

    # Port probe (fallback if ping blocked)
    check_ports = ports or [80, 443, 22, 8080, 554, 23, 8443]
    open_ports: list[int] = []
    for port in check_ports:
        try:
            t_port = time.monotonic()
            with socket.create_connection((ip, port), timeout=0.5):
                open_ports.append(port)
                if not reachable:
                    reachable = True
                    latency_ms = round((time.monotonic() - t_port) * 1000, 1)
        except Exception:
            pass

    return {"reachable": reachable, "latency_ms": latency_ms, "open_ports": open_ports}


def arp_single_ip(ip: str) -> str | None:
    """ARP-lookup a single IP → return MAC or None. Platform-aware."""
    backend = _create_arp_backend()
    return backend.scan_single(ip)


def _resolve_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def _run_arp_cache() -> tuple[int, str]:
    """Read the OS ARP cache (arp -a). Returns (returncode, text)."""
    try:
        r = subprocess.run(["arp", "-a"], capture_output=True, timeout=5)
        for enc in ("utf-8", "cp866", "cp1251"):
            try:
                return r.returncode, r.stdout.decode(enc)
            except Exception:
                continue
        return r.returncode, r.stdout.decode(errors="replace")
    except Exception as exc:
        return -1, str(exc)


def _scan_arp(network: str) -> list[DeviceInfo]:
    """Scan a CIDR network using platform-appropriate backend."""
    backend = _create_arp_backend()
    return backend.scan_network(network)


def _tcp_connect_scan(network: str, timeout: float = 0.35) -> list[str]:
    """Find live hosts via TCP connect to common ports.

    Works when ARP is blocked by client isolation (L3 routing still allowed).
    Uses ConnectionRefusedError (RST) as immediate "host is up" signal —
    no need to wait for full timeout if the host is up but port is closed.

    Returns list of live IPs (no MAC — caller must check ARP cache).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    PORTS = [80, 443, 22, 445, 3389, 8080, 23]

    try:
        net_obj = ipaddress.ip_network(network, strict=False)
    except ValueError:
        return []
    # Skip huge networks (>1024 hosts) to avoid long scans
    if net_obj.num_addresses > 1024:
        logger.info("TCP scan: skipping large network %s", network)
        return []

    hosts = [str(ip) for ip in net_obj.hosts()]
    live: list[str] = []

    def check(ip: str) -> str | None:
        for port in PORTS:
            try:
                with socket.create_connection((ip, port), timeout=timeout):
                    return ip  # connected → host is up
            except ConnectionRefusedError:
                return ip  # RST → port closed but host is up
            except OSError:
                pass  # timeout / filtered → try next port
        return None

    with ThreadPoolExecutor(max_workers=64) as pool:
        futures = {pool.submit(check, h): h for h in hosts}
        for f in as_completed(futures, timeout=20):
            try:
                result = f.result()
                if result:
                    live.append(result)
            except Exception:
                pass

    logger.info("TCP connect scan %s: %d live hosts", network, len(live))
    return live


class NetworkScanner:
    def __init__(self, interface: str | None = None) -> None:
        self._interface = interface  # None = auto-detect
        self._backend: ArpBackend = _create_arp_backend(interface)
        logger.info(
            "NetworkScanner: platform=%s backend=%s",
            platform.system(), self._backend.source_tag,
        )

    def _get_networks(self) -> list[str]:
        networks = detect_local_networks(self._interface)
        if networks:
            logger.info("ARP scan targets: %s", networks)
        else:
            logger.warning("No suitable network found for ARP scan")
        return networks

    def _enrich_with_arp_cache(self, ips: list[str]) -> list[DeviceInfo]:
        """Look up MACs for a list of IPs via ARP cache (arp -a)."""
        rc, text = _run_arp_cache()
        from app.discovery.backends.windows_arp import parse_arp_cache
        cache = dict(parse_arp_cache(text)) if rc == 0 else {}

        from app.discovery.classifier import guess_device_type
        from app.discovery.oui import get_oui_lookup
        oui = get_oui_lookup()
        now = datetime.now()
        devices: list[DeviceInfo] = []
        for ip in ips:
            mac = cache.get(ip, "")
            if not mac:
                # Generate placeholder MAC so device appears on map
                try:
                    parts = [int(x) for x in ip.split(".")]
                    mac = f"02:00:{parts[0]:02X}:{parts[1]:02X}:{parts[2]:02X}:{parts[3]:02X}"
                except Exception:
                    continue
            vendor = oui.lookup(mac)
            devices.append(DeviceInfo(
                mac=mac.upper(), ip=ip, vendor=vendor,
                device_type=guess_device_type(vendor=vendor, hostname=""),
                first_seen=now, last_seen=now, is_online=True,
            ))
        return devices

    def scan_once(self) -> list[DeviceInfo]:
        """ARP scan; fall back to TCP connect scan if ARP yields nothing."""
        networks = self._get_networks()
        if not networks:
            return []
        all_devices: list[DeviceInfo] = []
        for net in networks:
            try:
                found = self._backend.scan_network(net)
                all_devices.extend(found)
            except Exception as exc:
                logger.warning("ARP scan failed for %s: %s", net, exc)

        # If ARP found nothing (e.g. client isolation), try TCP connect scan
        if not all_devices:
            logger.info("ARP returned 0 devices — trying TCP connect scan")
            for net in networks:
                try:
                    live_ips = _tcp_connect_scan(net)
                    all_devices.extend(self._enrich_with_arp_cache(live_ips))
                except Exception as exc:
                    logger.warning("TCP scan failed for %s: %s", net, exc)

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
