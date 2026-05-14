"""Linux ARP discovery backend — uses Scapy srp."""

from __future__ import annotations

import socket
from datetime import datetime

from app.discovery.backends.base import ArpBackend
from app.discovery.models import DeviceInfo


class LinuxArpBackend(ArpBackend):
    @property
    def source_tag(self) -> str:
        return "scapy"

    def scan_network(self, network: str) -> list[DeviceInfo]:
        try:
            from scapy.layers.l2 import ARP, Ether  # type: ignore
            from scapy.sendrecv import srp  # type: ignore
        except ImportError:
            raise RuntimeError("scapy is not installed — ARP scan unavailable")

        from app.discovery.classifier import guess_device_type
        from app.discovery.oui import get_oui_lookup

        oui = get_oui_lookup()
        now = datetime.now()

        pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=network)
        answered, _ = srp(pkt, timeout=3, retry=2, verbose=False)

        devices: list[DeviceInfo] = []
        for _, rcv in answered:
            mac: str = rcv.hwsrc.upper()
            ip: str = rcv.psrc
            vendor = oui.lookup(mac)
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except Exception:
                hostname = ""
            device_type = guess_device_type(vendor=vendor, hostname=hostname)
            devices.append(DeviceInfo(
                mac=mac, ip=ip, vendor=vendor, device_type=device_type,
                hostname=hostname, first_seen=now, last_seen=now, is_online=True,
            ))
        return devices

    def scan_single(self, ip: str) -> str | None:
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
