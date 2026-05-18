from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from app.discovery.models import DeviceInfo
from app.discovery.risk import calculate_risk_score, risk_label as _risk_label

if TYPE_CHECKING:
    from app.contracts.schemas import InferenceResult, NormalizedFlowEvent


def _get_local_ips() -> set[str]:
    """Return all IPv4 addresses assigned to local interfaces."""
    ips: set[str] = set()
    try:
        import socket
        import psutil
        for addrs in psutil.net_if_addrs().values():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ips.add(addr.address)
    except Exception:
        pass
    return ips


class DeviceTracker:
    """Tracks discovered devices and enriches them with pipeline alert data."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._devices: dict[str, DeviceInfo] = {}          # mac → DeviceInfo
        self._ip_to_mac: dict[str, str] = {}               # ip → mac
        self._alert_history: dict[str, deque] = {}         # mac → deque(maxlen=50)
        self._traffic: dict[str, deque] = {}               # ip → deque[(ts, b_in, b_out)]
        self._last_scan: Optional[datetime] = None
        self._local_ips: set[str] = _get_local_ips()

    # ── Scan integration ──────────────────────────────────────

    def merge_scan_results(self, scanned: list[DeviceInfo]) -> None:
        now = datetime.now()
        with self._lock:
            seen_macs = {d.mac.upper() for d in scanned}

            for d in scanned:
                if d.mac in self._devices:
                    existing = self._devices[d.mac]
                    existing.ip = d.ip
                    existing.last_seen = now
                    existing.is_online = d.is_online
                    if d.hostname and existing.hostname != d.hostname:
                        existing.hostname = d.hostname
                    if d.vendor != "Unknown" and existing.vendor != d.vendor:
                        existing.vendor = d.vendor
                    if existing.device_type == "unknown" and (existing.hostname or existing.vendor != "Unknown"):
                        from app.discovery.classifier import guess_device_type
                        new_type = guess_device_type(vendor=existing.vendor, hostname=existing.hostname)
                        if new_type != "unknown":
                            existing.device_type = new_type
                else:
                    score = calculate_risk_score(d)
                    d.risk_score = score
                    d.risk_label = _risk_label(score)
                    d.is_self = d.ip in self._local_ips
                    self._devices[d.mac] = d
                    self._alert_history[d.mac] = deque(maxlen=50)
                self._ip_to_mac[d.ip] = d.mac

            # Mark devices not in this scan as offline
            for mac, dev in self._devices.items():
                if mac not in seen_macs:
                    dev.is_online = False

            self._last_scan = now

    # ── Pipeline hook ─────────────────────────────────────────

    def on_flow_event(self, event: "NormalizedFlowEvent", inference: "InferenceResult") -> None:
        src_ip = getattr(event, "src_ip", None)
        if not src_ip:
            return

        now = datetime.now()
        b_in = getattr(event, "bytes_in", 0) or 0
        b_out = getattr(event, "bytes_out", 0) or 0

        with self._lock:
            mac = self._ip_to_mac.get(src_ip)
            if mac:
                mac = mac.upper()

            if mac and mac in self._devices:
                dev = self._devices[mac]
                dev.last_seen = now
                dev.bytes_in += b_in
                dev.bytes_out += b_out

                label = getattr(inference, "label", "normal")
                if label in ("warning", "anomaly"):
                    dev.is_suspicious = True
                    dev.alert_count += 1
                    dev.last_alert_type = getattr(inference, "attack_class", None) or label
                    dev.last_alert_score = getattr(inference, "score", None)
                    dev.last_alert_time = now

                    self._alert_history[mac].append({
                        "ts": now.isoformat(),
                        "label": label,
                        "attack_class": getattr(inference, "attack_class", None),
                        "score": getattr(inference, "score", None),
                        "src_ip": src_ip,
                        "dst_ip": getattr(event, "dst_ip", None),
                    })

                score = calculate_risk_score(dev)
                dev.risk_score = score
                dev.risk_label = _risk_label(score)

            # Track traffic window even for unknown IPs (may be added later by scan)
            if src_ip not in self._traffic:
                self._traffic[src_ip] = deque(maxlen=300)
            self._traffic[src_ip].append((now, b_in, b_out))

    # ── Passive L2 discovery ──────────────────────────────────

    def on_passive_arp(self, src_ip: str, src_mac: str, hostname: str = "") -> None:
        """Called from capture adapter when an L2 frame reveals IP→MAC mapping.

        Works without active ARP scans — extracts info from ARP/DHCP/mDNS/SSDP
        broadcasts and unicast frames addressed to this host. Thread-safe.
        """
        import ipaddress as _ip
        try:
            addr = _ip.ip_address(src_ip)
            if not addr.is_private or addr.is_loopback or addr.is_link_local:
                return
        except ValueError:
            return

        mac = src_mac.upper()
        if mac in ("FF:FF:FF:FF:FF:FF", "00:00:00:00:00:00"):
            return
        # skip multicast MACs (odd first byte)
        try:
            if int(mac.split(":")[0], 16) & 1:
                return
        except Exception:
            return

        now = datetime.now()
        with self._lock:
            existing_mac = self._ip_to_mac.get(src_ip)
            if existing_mac and existing_mac.upper() != mac:
                old_dev = self._devices.get(existing_mac.upper())
                if old_dev:
                    old_dev.is_online = False

            if mac in self._devices:
                dev = self._devices[mac]
                dev.ip = src_ip
                dev.last_seen = now
                dev.is_online = True
                self._ip_to_mac[src_ip] = mac
                # Update hostname if we got a better one (e.g. from DHCP)
                if hostname and not dev.hostname and not dev.custom_name:
                    dev.hostname = hostname
                    if dev.device_type == "unknown":
                        from app.discovery.classifier import guess_device_type
                        new_type = guess_device_type(vendor=dev.vendor, hostname=hostname)
                        if new_type != "unknown":
                            dev.device_type = new_type
                return

            try:
                from app.discovery.oui import get_oui_lookup
                vendor = get_oui_lookup().lookup(mac)
            except Exception:
                vendor = "Unknown"
            # Use provided hostname (DHCP/mDNS); fallback to DNS reverse lookup
            resolved_hostname = hostname
            if not resolved_hostname:
                try:
                    import socket as _sock
                    resolved_hostname = _sock.gethostbyaddr(src_ip)[0]
                except Exception:
                    resolved_hostname = ""
            try:
                from app.discovery.classifier import guess_device_type
                device_type = guess_device_type(vendor=vendor, hostname=resolved_hostname)
            except Exception:
                device_type = "unknown"

            dev = DeviceInfo(
                mac=mac, ip=src_ip, vendor=vendor,
                device_type=device_type, hostname=resolved_hostname,
                first_seen=now, last_seen=now, is_online=True,
                is_self=(src_ip in self._local_ips),
            )
            from app.discovery.risk import calculate_risk_score, risk_label as _risk_label
            score = calculate_risk_score(dev)
            dev.risk_score = score
            dev.risk_label = _risk_label(score)
            self._devices[mac] = dev
            self._alert_history[mac] = deque(maxlen=50)
            self._ip_to_mac[src_ip] = mac

    # ── DNS integration ──────────────────────────────────────

    def on_dns_alert(self, src_ip: str) -> None:
        """Called from dns_monitor callback (scapy thread) when DGA/tunneling is detected."""
        now = datetime.now()
        with self._lock:
            mac = self._ip_to_mac.get(src_ip)
            if not mac:
                return
            dev = self._devices.get(mac.upper())
            if not dev:
                return
            dev.dns_alert_count += 1
            dev.last_dns_alert = now
            dev.is_suspicious = True
            score = calculate_risk_score(dev)
            dev.risk_score = score
            dev.risk_label = _risk_label(score)

    # ── Queries ───────────────────────────────────────────────

    def get_all_devices(self) -> list[DeviceInfo]:
        with self._lock:
            devices = list(self._devices.values())
        # suspicious first, then online, then offline
        return sorted(devices, key=lambda d: (not d.is_suspicious, not d.is_online, d.ip))

    def get_bytes_last_5min(self, ip: str) -> tuple[int, int]:
        cutoff = datetime.now() - timedelta(minutes=5)
        with self._lock:
            window = self._traffic.get(ip, deque())
            b_in = sum(b for ts, b, _ in window if ts >= cutoff)
            b_out = sum(b for ts, _, b in window if ts >= cutoff)
        return b_in, b_out

    def get_alert_history(self, mac: str) -> list[dict]:
        with self._lock:
            return list(self._alert_history.get(mac.upper(), []))

    def get_device_by_mac(self, mac: str) -> Optional[DeviceInfo]:
        with self._lock:
            return self._devices.get(mac.upper())

    def get_device_by_ip(self, ip: str) -> Optional[DeviceInfo]:
        with self._lock:
            mac = self._ip_to_mac.get(ip)
            if mac is None:
                return None
            return self._devices.get(mac.upper())

    def reset_suspicious(self, mac: str) -> None:
        with self._lock:
            dev = self._devices.get(mac.upper())
            if dev:
                dev.is_suspicious = False
                dev.alert_count = 0
                dev.last_alert_type = None
                dev.last_alert_score = None
                dev.last_alert_time = None
                self._alert_history.get(mac.upper(), deque()).clear()

    def set_label(self, mac: str, label: str, device_type: str) -> None:
        with self._lock:
            dev = self._devices.get(mac.upper())
            if dev:
                dev.custom_name = label
                dev.device_type = device_type

    def add_device_manual(
        self,
        ip: str,
        mac: str,
        custom_name: str = "",
        device_type: str = "unknown",
        vendor: str = "Unknown",
    ) -> DeviceInfo:
        mac = mac.upper()
        now = datetime.now()
        with self._lock:
            if mac in self._devices:
                dev = self._devices[mac]
                dev.ip = ip
                if custom_name:
                    dev.custom_name = custom_name
                if device_type != "unknown":
                    dev.device_type = device_type
                dev.last_seen = now
            else:
                dev = DeviceInfo(
                    mac=mac, ip=ip, vendor=vendor,
                    device_type=device_type, custom_name=custom_name,
                    first_seen=now, last_seen=now, is_online=True,
                )
                self._devices[mac] = dev
                self._alert_history[mac] = deque(maxlen=50)
            self._ip_to_mac[ip] = mac
        return dev

    def remove_device(self, mac: str) -> bool:
        mac = mac.upper()
        with self._lock:
            if mac not in self._devices:
                return False
            dev = self._devices.pop(mac)
            self._ip_to_mac.pop(dev.ip, None)
            self._alert_history.pop(mac, None)
        return True

    def set_whitelisted(self, mac: str, value: bool) -> None:
        with self._lock:
            dev = self._devices.get(mac.upper())
            if dev:
                dev.is_whitelisted = value

    def get_stats(self) -> dict:
        with self._lock:
            devices = list(self._devices.values())
        total = len(devices)
        online = sum(1 for d in devices if d.is_online)
        suspicious = sum(1 for d in devices if d.is_suspicious)
        whitelisted = sum(1 for d in devices if d.is_whitelisted)
        by_type: dict[str, int] = {}
        for d in devices:
            by_type[d.device_type] = by_type.get(d.device_type, 0) + 1
        return {
            "total": total,
            "online": online,
            "offline": total - online,
            "suspicious": suspicious,
            "whitelisted": whitelisted,
            "by_type": by_type,
            "last_scan": self._last_scan.isoformat() if self._last_scan else None,
        }
