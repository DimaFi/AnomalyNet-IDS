"""Unit tests for DNS anomaly detection in DnsMonitor._check()."""
import pytest
from app.dns.monitor import DnsMonitor


@pytest.fixture
def mon() -> DnsMonitor:
    return DnsMonitor()


def test_dga_detected(mon: DnsMonitor) -> None:
    # 18 unique chars → H = log2(18) ≈ 4.17 > 4.0; digit_ratio = 9/18 = 0.50 >= 0.15
    alert = mon._check("1.2.3.4", "a1b2c3d4e5f6g7h8i9.evil.com")
    assert alert is not None
    assert alert["type"] == "DGA_DOMAIN"
    assert alert["entropy"] is not None
    assert alert["src_ip"] == "1.2.3.4"


def test_normal_domain_not_detected(mon: DnsMonitor) -> None:
    # Long but human-readable, no digits — should NOT trigger DGA
    assert mon._check("1.2.3.4", "firebaseremoteconfig.googleapis.com") is None


def test_short_label_not_detected(mon: DnsMonitor) -> None:
    # Short label — length check prevents FP on short random-looking strings
    assert mon._check("1.2.3.4", "a1b.evil.com") is None


def test_digit_ratio_required(mon: DnsMonitor) -> None:
    # High entropy but no digits — should NOT trigger DGA
    # "qwertyzxcvbnm" is somewhat random but has zero digits
    assert mon._check("1.2.3.4", "qwertyzxcvbnmasd.evil.com") is None


def test_tunneling_detected(mon: DnsMonitor) -> None:
    long_label = "a" * 51
    alert = mon._check("1.2.3.4", f"{long_label}.evil.com")
    assert alert is not None
    assert alert["type"] == "DNS_TUNNELING"


def test_tunneling_threshold_exact(mon: DnsMonitor) -> None:
    # Exactly 50 chars — should NOT trigger (> 50 required)
    label = "a" * 50
    assert mon._check("1.2.3.4", f"{label}.evil.com") is None


def test_callback_called_on_alert(mon: DnsMonitor) -> None:
    received: list[dict] = []
    mon.set_alert_callback(received.append)

    # Normal domain — no callback
    mon.on_dns_packet("1.2.3.4", "google.com", "A")
    assert len(received) == 0

    # Tunneling domain — callback fires
    mon.on_dns_packet("1.2.3.4", "a" * 55 + ".evil.com", "A")
    assert len(received) == 1
    assert received[0]["type"] == "DNS_TUNNELING"


def test_callback_exception_does_not_crash(mon: DnsMonitor) -> None:
    def bad_cb(_: dict) -> None:
        raise RuntimeError("broken callback")

    mon.set_alert_callback(bad_cb)
    # Should not raise even though callback raises
    mon.on_dns_packet("1.2.3.4", "a" * 55 + ".evil.com", "A")
