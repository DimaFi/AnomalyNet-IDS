from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


DEVICE_TYPES: dict[str, dict[str, str]] = {
    "iot_camera":   {"label": "IP-камера",       "emoji": "📷"},
    "iot_sensor":   {"label": "IoT датчик",       "emoji": "📡"},
    "iot_bulb":     {"label": "Умная лампа",      "emoji": "💡"},
    "iot_plug":     {"label": "Умная розетка",    "emoji": "🔌"},
    "router":       {"label": "Роутер/шлюз",      "emoji": "🌐"},
    "pc_windows":   {"label": "Windows ПК",       "emoji": "💻"},
    "pc_linux":     {"label": "Linux сервер",     "emoji": "🐧"},
    "pc_mac":       {"label": "Mac",              "emoji": "🍎"},
    "phone":        {"label": "Смартфон",         "emoji": "📱"},
    "printer":      {"label": "Принтер",          "emoji": "🖨"},
    "nas":          {"label": "NAS хранилище",    "emoji": "💾"},
    "game_console": {"label": "Игровая консоль",  "emoji": "🎮"},
    "tv":           {"label": "Смарт ТВ",         "emoji": "📺"},
    "unknown":      {"label": "Неизвестно",       "emoji": "❓"},
}


@dataclass
class DeviceInfo:
    mac: str
    ip: str
    vendor: str = "Unknown"
    device_type: str = "unknown"
    hostname: str = ""
    custom_name: str = ""
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    is_online: bool = True
    is_suspicious: bool = False
    is_whitelisted: bool = False
    alert_count: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    last_alert_type: Optional[str] = None
    last_alert_score: Optional[float] = None
    last_alert_time: Optional[datetime] = None
    open_ports: list[int] = field(default_factory=list)
    risk_score: int = 0
    risk_label: str = "low"

    def display_name(self) -> str:
        return self.custom_name or self.hostname or self.vendor or self.ip

    def to_dict(self) -> dict:
        def _dt(v: Optional[datetime]) -> Optional[str]:
            return v.isoformat() if v else None

        return {
            "mac": self.mac,
            "ip": self.ip,
            "vendor": self.vendor,
            "device_type": self.device_type,
            "display_name": self.display_name(),
            "hostname": self.hostname,
            "custom_name": self.custom_name,
            "first_seen": _dt(self.first_seen),
            "last_seen": _dt(self.last_seen),
            "is_online": self.is_online,
            "is_suspicious": self.is_suspicious,
            "is_whitelisted": self.is_whitelisted,
            "alert_count": self.alert_count,
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
            "last_alert_type": self.last_alert_type,
            "last_alert_score": self.last_alert_score,
            "last_alert_time": _dt(self.last_alert_time),
            "open_ports": self.open_ports,
            "risk_score": self.risk_score,
            "risk_label": self.risk_label,
            "device_label": DEVICE_TYPES.get(self.device_type, DEVICE_TYPES["unknown"])["label"],
            "device_emoji": DEVICE_TYPES.get(self.device_type, DEVICE_TYPES["unknown"])["emoji"],
        }
