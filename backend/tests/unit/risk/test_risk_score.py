"""Unit tests for calculate_risk_score() and risk_label()."""
import pytest
from app.discovery.models import DeviceInfo
from app.discovery.risk import calculate_risk_score, risk_label


def make_device(**kwargs) -> DeviceInfo:
    defaults = dict(mac="AA:BB:CC:DD:EE:FF", ip="192.168.1.1", device_type="unknown")
    defaults.update(kwargs)
    return DeviceInfo(**defaults)


# ── Baseline (no alerts) ─────────────────────────────────────────────────────

def test_zero_alerts_baseline() -> None:
    # type_score for "unknown" = 50, weight 10% → score = 5
    dev = make_device(device_type="unknown")
    assert calculate_risk_score(dev) == 5


def test_low_risk_safe_device() -> None:
    # phone: type_score=20, weight 10% → 2
    dev = make_device(device_type="phone")
    assert calculate_risk_score(dev) == 2


def test_router_baseline_higher() -> None:
    # router: type_score=80, weight 10% → 8
    dev = make_device(device_type="router")
    assert calculate_risk_score(dev) == 8


# ── ML alerts only ───────────────────────────────────────────────────────────

def test_few_ml_alerts() -> None:
    dev = make_device(alert_count=3, last_alert_score=0.80, device_type="pc_windows")
    score = calculate_risk_score(dev)
    # ml_s=20 * 0.40 + sev_s=60 * 0.25 + dns_s=0 + type_s=30 * 0.10
    # = 8 + 15 + 0 + 3 = 26
    assert score == 26


def test_many_ml_alerts_critical() -> None:
    dev = make_device(alert_count=100, last_alert_score=0.95, device_type="iot_camera")
    score = calculate_risk_score(dev)
    # ml_s=100*0.40 + 100*0.25 + 0 + 60*0.10 = 40+25+6 = 71
    assert score == 71


# ── DNS alerts only ──────────────────────────────────────────────────────────

def test_dns_alerts_increase_risk() -> None:
    dev_clean = make_device(device_type="pc_windows")
    dev_dns   = make_device(device_type="pc_windows", dns_alert_count=3)
    assert calculate_risk_score(dev_dns) > calculate_risk_score(dev_clean)


def test_single_dns_alert_not_critical() -> None:
    # One DNS alert alone should not push to critical (>= 75)
    dev = make_device(dns_alert_count=1, device_type="phone")
    assert calculate_risk_score(dev) < 75


def test_many_dns_alerts() -> None:
    dev = make_device(dns_alert_count=10, device_type="unknown")
    score = calculate_risk_score(dev)
    # dns_s=100 * 0.25 + type_s=50 * 0.10 = 25 + 5 = 30
    assert score == 30


# ── Combined ML + DNS ────────────────────────────────────────────────────────

def test_combined_ml_and_dns() -> None:
    dev_ml_only  = make_device(alert_count=10, last_alert_score=0.92, device_type="iot_camera")
    dev_combined = make_device(alert_count=10, last_alert_score=0.92, dns_alert_count=4, device_type="iot_camera")
    assert calculate_risk_score(dev_combined) > calculate_risk_score(dev_ml_only)


def test_score_clamped_to_100() -> None:
    dev = make_device(alert_count=200, last_alert_score=0.99, dns_alert_count=50, device_type="router")
    assert calculate_risk_score(dev) <= 100


def test_score_not_negative() -> None:
    dev = make_device()
    assert calculate_risk_score(dev) >= 0


# ── risk_label ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,expected", [
    (0, "low"), (24, "low"),
    (25, "medium"), (49, "medium"),
    (50, "high"), (74, "high"),
    (75, "critical"), (100, "critical"),
])
def test_risk_label_boundaries(score: int, expected: str) -> None:
    assert risk_label(score) == expected
