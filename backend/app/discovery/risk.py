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
    """Return integer 0-100 risk score.

    Components (weighted):
      ml_alert_score  40% — based on ML flow alert_count
      severity_score  25% — based on last ML alert score
      dns_score       25% — based on dns_alert_count
      type_score      10% — based on device_type
    """
    # ml_alert_score
    n = device.alert_count
    if n == 0:
        ml_s = 0
    elif n <= 5:
        ml_s = 20
    elif n <= 20:
        ml_s = 50
    elif n <= 50:
        ml_s = 75
    else:
        ml_s = 100

    # severity_score (last ML alert confidence)
    sc = device.last_alert_score
    if sc is None:
        sev_s = 0
    elif sc < 0.75:
        sev_s = 30
    elif sc <= 0.90:
        sev_s = 60
    else:
        sev_s = 100

    # dns_score — one stray alert shouldn't make critical; needs 6+ to reach 100
    d = device.dns_alert_count
    if d == 0:
        dns_s = 0
    elif d <= 2:
        dns_s = 30
    elif d <= 5:
        dns_s = 60
    else:
        dns_s = 100

    # device_type_score
    type_s = _DEVICE_TYPE_RISK.get(device.device_type, 50)

    score = round(ml_s * 0.40 + sev_s * 0.25 + dns_s * 0.25 + type_s * 0.10)
    return max(0, min(100, score))


def risk_label(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"
