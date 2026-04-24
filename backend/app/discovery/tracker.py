from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from app.discovery.models import DeviceInfo

if TYPE_CHECKING:
    from app.contracts.schemas import InferenceResult, NormalizedFlowEvent


class DeviceTracker:
    """Tracks discovered devices and enriches them with pipeline alert data."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._devices: dict[str, DeviceInfo] = {}          # mac → DeviceInfo
        self._ip_to_mac: dict[str, str] = {}               # ip → mac
        self._alert_history: dict[str, deque] = {}         # mac → deque(maxlen=50)
        self._traffic: dict[str, deque] = {}               # ip → deque[(ts, b_in, b_out)]
        self._last_scan: Optional[datetime] = None

    # ── Scan integration ──────────────────────────────────────

    def merge_scan_results(self, scanned: list[DeviceInfo]) -> None:
        now = datetime.now()
        with self._lock:
            seen_macs = {d.mac for d in scanned}

            for d in scanned:
                if d.mac in self._devices:
                    existing = self._devices[d.mac]
                    existing.ip = d.ip
                    existing.last_seen = now
                    existing.is_online = d.is_online
                    if d.hostname:
                        existing.hostname = d.hostname
                    if d.vendor != "Unknown":
                        existing.vendor = d.vendor
                else:
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

            # Track traffic window even for unknown IPs (may be added later by scan)
            if src_ip not in self._traffic:
                self._traffic[src_ip] = deque(maxlen=300)
            self._traffic[src_ip].append((now, b_in, b_out))

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
            return list(self._alert_history.get(mac, []))

    def get_device_by_mac(self, mac: str) -> Optional[DeviceInfo]:
        with self._lock:
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
