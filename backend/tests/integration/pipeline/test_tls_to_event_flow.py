"""Integration test: TLSMonitor alert → tls_alert_to_pipeline_event → store → history."""
import json
from pathlib import Path

import pytest

from app.tls.events import tls_alert_to_pipeline_event
from app.tls.monitor import TLSMonitor


# ── Helper ────────────────────────────────────────────────────────────────────

class _StubStore:
    def __init__(self, history_dir: Path) -> None:
        self._dir = history_dir
        self.written: list[dict] = []

    def append_history(self, event) -> None:
        data = event.model_dump(mode="json")
        self.written.append(data)
        day_path = self._dir / "test_day.ndjson"
        with day_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


def _fp(ja4: str = "t130203_aabbcc112233_ddeeff445566") -> dict:
    return {
        "ja4": ja4,
        "sni": "example.com",
        "alpn": "h2",
        "tls_version": "TLS 1.3",
        "cipher_count": 3,
        "ext_count": 6,
    }


SRC = "192.168.1.10"
DST = "93.184.216.34"
PORT = 443


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_tls_alert_written_to_history(tmp_history_dir: Path) -> None:
    """NEW_TLS_FINGERPRINT alert → event_type='tls' in history."""
    store = _StubStore(tmp_history_dir)
    monitor = TLSMonitor()

    def on_alert(alert: dict) -> None:
        ev = tls_alert_to_pipeline_event(alert)
        store.append_history(ev)

    monitor.set_alert_callback(on_alert)
    monitor.on_fingerprint(SRC, DST, PORT, _fp("fp_unique_abc"))

    assert len(store.written) == 1
    ev = store.written[0]
    assert ev["event_type"] == "tls"
    assert ev["priority"] == "medium"
    assert ev["metadata"]["tls_alert_type"] == "NEW_TLS_FINGERPRINT"


def test_event_metadata_contains_ja4(tmp_history_dir: Path) -> None:
    """Stored event metadata must include the ja4 fingerprint value."""
    store = _StubStore(tmp_history_dir)
    monitor = TLSMonitor()
    monitor.set_alert_callback(lambda a: store.append_history(tls_alert_to_pipeline_event(a)))

    monitor.on_fingerprint(SRC, DST, PORT, _fp("fp_meta_check"))

    assert len(store.written) == 1
    metadata = store.written[0]["metadata"]
    assert metadata["ja4"] == "fp_meta_check"
    assert metadata["sni"] == "example.com"
    assert metadata["alpn"] == "h2"


def test_same_fingerprint_not_written_twice(tmp_history_dir: Path) -> None:
    """Identical ja4 repeated for same src_ip → only one event stored."""
    store = _StubStore(tmp_history_dir)
    monitor = TLSMonitor()
    monitor.set_alert_callback(lambda a: store.append_history(tls_alert_to_pipeline_event(a)))

    monitor.on_fingerprint(SRC, DST, PORT, _fp("fp_repeat"))
    monitor.on_fingerprint(SRC, DST, PORT, _fp("fp_repeat"))
    monitor.on_fingerprint(SRC, DST, PORT, _fp("fp_repeat"))

    assert len(store.written) == 1


def test_too_many_event_written_with_correct_score(tmp_history_dir: Path) -> None:
    """TOO_MANY_TLS_FINGERPRINTS alert → score=0.7 in history."""
    store = _StubStore(tmp_history_dir)
    monitor = TLSMonitor(max_fingerprints_per_ip=2, window_seconds=3600)
    monitor.set_alert_callback(lambda a: store.append_history(tls_alert_to_pipeline_event(a)))

    for i in range(3):
        monitor.on_fingerprint(SRC, DST, PORT, _fp(f"fp_{i}"))

    too_many_events = [
        ev for ev in store.written
        if ev["metadata"]["tls_alert_type"] == "TOO_MANY_TLS_FINGERPRINTS"
    ]
    assert len(too_many_events) == 1
    assert too_many_events[0]["inference"]["score"] == 0.7


def test_event_in_ndjson_file(tmp_history_dir: Path) -> None:
    """Written event is parseable JSON in the NDJSON file."""
    store = _StubStore(tmp_history_dir)
    monitor = TLSMonitor()
    monitor.set_alert_callback(lambda a: store.append_history(tls_alert_to_pipeline_event(a)))

    monitor.on_fingerprint(SRC, DST, PORT, _fp("fp_ndjson_check"))

    ndjson_file = tmp_history_dir / "test_day.ndjson"
    assert ndjson_file.exists()
    lines = [l for l in ndjson_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_type"] == "tls"
    assert record["event"]["protocol"] == "TLS"
    assert record["event"]["src_ip"] == SRC
