from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.discovery.models import DeviceInfo

_DEVICE_TYPE_RISK: dict[str, int] = {
    "router":       80,
    "nas":          80,
    "iot_camera":   60,
    "iot_sensor":   40,
    "iot_plug":     40,
    "iot_bulb":     30,
    "pc_windows":   30,
    "pc_linux":     30,
    "pc_mac":       20,
    "phone":        20,
    "game_console": 20,
    "printer":      25,
    "tv":           20,
    "unknown":      50,
}


def calculate_risk_score(device: "DeviceInfo") -> int:
    """Return integer 0-100 risk score for a device.

    Components (each 0-100, weighted):
      - alert_score    50%: based on alert_count
      - severity_score 30%: based on last_alert_score
      - type_score     20%: based on device_type
    """
    # alert_score
    n = device.alert_count
    if n == 0:
        alert_s = 0
    elif n <= 5:
        alert_s = 20
    elif n <= 20:
        alert_s = 50
    elif n <= 50:
        alert_s = 75
    else:
        alert_s = 100

    # severity_score
    sc = device.last_alert_score
    if sc is None:
        sev_s = 0
    elif sc < 0.75:
        sev_s = 30
    elif sc <= 0.90:
        sev_s = 60
    else:
        sev_s = 100

    # device_type_score
    type_s = _DEVICE_TYPE_RISK.get(device.device_type, 50)

    score = round(alert_s * 0.5 + sev_s * 0.3 + type_s * 0.2)
    return max(0, min(100, score))


def risk_label(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"
