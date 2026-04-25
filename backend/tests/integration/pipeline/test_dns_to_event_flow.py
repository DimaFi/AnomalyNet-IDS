"""Integration test: DnsMonitor alert → dns_alert_to_pipeline_event → JsonFileStore → history file."""
import json
from pathlib import Path

import pytest

from app.dns.events import dns_alert_to_pipeline_event
from app.dns.monitor import DnsMonitor


# ── Helper: minimal write-only storage stub ──────────────────────────────────

class _StubStore:
    """Minimal stub — only implements append_history()."""

    def __init__(self, history_dir: Path) -> None:
        self._dir = history_dir
        self.written: list[dict] = []

    def append_history(self, event) -> None:
        data = event.model_dump(mode="json")
        self.written.append(data)
        day_path = self._dir / "test_day.ndjson"
        with day_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


# ── Tests ────────────────────────────────────────────────────────────────────

def test_dns_alert_written_to_history(tmp_history_dir: Path) -> None:
    store = _StubStore(tmp_history_dir)
    monitor = DnsMonitor()

    def on_alert(alert: dict) -> None:
        ev = dns_alert_to_pipeline_event(alert)
        store.append_history(ev)

    monitor.set_alert_callback(on_alert)

    # Trigger a tunneling detection
    tunneling_domain = "a" * 55 + ".evil.com"
    monitor.on_dns_packet("192.168.1.50", tunneling_domain, "A")

    # Exactly one event should be written
    assert len(store.written) == 1
    ev_data = store.written[0]
    assert ev_data["event_type"] == "dns"
    assert ev_data["priority"] == "high"
    assert ev_data["metadata"]["dns_alert_type"] == "DNS_TUNNELING"


def test_dns_event_present_in_ndjson_file(tmp_history_dir: Path) -> None:
    store = _StubStore(tmp_history_dir)
    monitor = DnsMonitor()

    monitor.set_alert_callback(lambda a: store.append_history(dns_alert_to_pipeline_event(a)))

    # Trigger DGA detection: 18 unique chars → H ≈ 4.17 > 4.0, digit_ratio 0.50
    dga_domain = "a1b2c3d4e5f6g7h8i9.evil.com"
    monitor.on_dns_packet("192.168.1.10", dga_domain, "A")

    ndjson_file = tmp_history_dir / "test_day.ndjson"
    assert ndjson_file.exists()

    lines = [l for l in ndjson_file.read_text().splitlines() if l.strip()]
    assert len(lines) >= 1

    record = json.loads(lines[0])
    assert record["event_type"] == "dns"
    assert record["metadata"]["domain"] == dga_domain


def test_normal_domain_does_not_write_to_history(tmp_history_dir: Path) -> None:
    store = _StubStore(tmp_history_dir)
    monitor = DnsMonitor()
    monitor.set_alert_callback(lambda a: store.append_history(dns_alert_to_pipeline_event(a)))

    monitor.on_dns_packet("192.168.1.10", "google.com", "A")
    monitor.on_dns_packet("192.168.1.10", "firebaseremoteconfig.googleapis.com", "A")

    assert len(store.written) == 0


def test_multiple_alerts_all_written(tmp_history_dir: Path) -> None:
    store = _StubStore(tmp_history_dir)
    monitor = DnsMonitor()
    monitor.set_alert_callback(lambda a: store.append_history(dns_alert_to_pipeline_event(a)))

    monitor.on_dns_packet("10.0.0.1", "a" * 55 + ".c1.com", "A")  # tunneling
    monitor.on_dns_packet("10.0.0.2", "a" * 55 + ".c2.com", "A")  # tunneling

    assert len(store.written) == 2
    src_ips = {ev["event"]["src_ip"] for ev in store.written}
    assert "10.0.0.1" in src_ips
    assert "10.0.0.2" in src_ips
