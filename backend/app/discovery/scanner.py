from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from datetime import datetime
from typing import TYPE_CHECKING

from app.discovery.classifier import guess_device_type
from app.discovery.models import DeviceInfo
from app.discovery.oui import get_oui_lookup

if TYPE_CHECKING:
    from app.discovery.tracker import DeviceTracker

logger = logging.getLogger(__name__)

MOCK_DEVICES: list[tuple[str, str, str, str, str, bool, bool]] = [
    # (mac,                  ip,             vendor,      device_type,   hostname,      is_suspicious, is_online)
    ("00:11:22:33:44:01", "192.168.1.1",   "TP-Link",   "router",      "router",      False, True),
    ("00:11:22:33:44:02", "192.168.1.10",  "Hikvision", "iot_camera",  "cam-front",   True,  True),
    ("00:11:22:33:44:03", "192.168.1.11",  "Reolink",   "iot_camera",  "cam-back",    False, True),
    ("00:11:22:33:44:04", "192.168.1.20",  "Espressif", "iot_sensor",  "sensor-01",   False, True),
    ("00:11:22:33:44:05", "192.168.1.30",  "Microsoft", "pc_windows",  "DESKTOP-ABC", False, True),
    ("00:11:22:33:44:06", "192.168.1.50",  "Apple",     "phone",       "iPhone-X",    False, False),
    ("00:11:22:33:44:07", "192.168.1.60",  "Philips",   "iot_bulb",    "hue-lamp",    False, True),
]


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
    def __init__(self, is_mock: bool = False, network: str = "192.168.1.0/24") -> None:
        self._is_mock = is_mock
        self._network = network

    def scan_once(self) -> list[DeviceInfo]:
        if self._is_mock:
            return self._mock_devices()
        return _scan_arp(self._network)

    def _mock_devices(self) -> list[DeviceInfo]:
        now = datetime.now()
        result = []
        for mac, ip, vendor, device_type, hostname, is_suspicious, is_online in MOCK_DEVICES:
            result.append(DeviceInfo(
                mac=mac, ip=ip, vendor=vendor, device_type=device_type,
                hostname=hostname, first_seen=now, last_seen=now,
                is_online=is_online, is_suspicious=is_suspicious,
            ))
        return result

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
