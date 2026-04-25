"""Unit tests for DNS event conversion and export format."""
import json
import pytest
from app.dns.events import dns_alert_to_pipeline_event


def _dga_alert(src_ip: str = "192.168.1.10") -> dict:
    return {
        "type": "DGA_DOMAIN",
        "domain": "a1b2c3d4e5f6.evil.com",
        "src_ip": src_ip,
        "entropy": 4.5,
        "description": "Possible DGA domain: entropy 4.50, digits 50%",
    }


def _tunneling_alert(src_ip: str = "192.168.1.20") -> dict:
    return {
        "type": "DNS_TUNNELING",
        "domain": ("x" * 60) + ".evil.com",
        "src_ip": src_ip,
        "entropy": None,
        "description": "DNS tunneling suspected",
    }


# ── PipelineEvent fields ─────────────────────────────────────────────────────

def test_event_type_is_dns() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    assert ev.event_type == "dns"


def test_event_protocol_is_dns() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    assert ev.event.protocol == "DNS"


def test_priority_is_high_for_dga() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    assert ev.priority == "high"


def test_priority_is_high_for_tunneling() -> None:
    ev = dns_alert_to_pipeline_event(_tunneling_alert())
    assert ev.priority == "high"


def test_mitre_populated_for_dga() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    assert ev.mitre is not None
    assert "T1568" in ev.mitre["id"]


def test_mitre_populated_for_tunneling() -> None:
    ev = dns_alert_to_pipeline_event(_tunneling_alert())
    assert ev.mitre is not None
    assert "T1071" in ev.mitre["id"]


def test_metadata_contains_domain() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    assert ev.metadata is not None
    assert ev.metadata["domain"] == "a1b2c3d4e5f6.evil.com"


def test_metadata_contains_entropy() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    assert ev.metadata["entropy"] == 4.5


def test_metadata_transport_is_udp() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    assert ev.metadata["transport"] == "UDP"


def test_inference_label_is_anomaly() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    assert ev.inference.label == "anomaly"


def test_inference_score_normalized() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    assert 0.0 <= ev.inference.score <= 1.0


def test_tunneling_score_is_one_when_no_entropy() -> None:
    ev = dns_alert_to_pipeline_event(_tunneling_alert())
    assert ev.inference.score == 1.0


def test_src_ip_preserved() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert(src_ip="10.0.0.5"))
    assert ev.event.src_ip == "10.0.0.5"


# ── Serialization (model_dump) ───────────────────────────────────────────────

def test_model_dump_contains_event_type() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    data = ev.model_dump(mode="json")
    assert data["event_type"] == "dns"


def test_model_dump_contains_metadata() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    data = ev.model_dump(mode="json")
    assert data["metadata"]["domain"] == "a1b2c3d4e5f6.evil.com"


def test_model_dump_is_json_serializable() -> None:
    ev = dns_alert_to_pipeline_event(_dga_alert())
    data = ev.model_dump(mode="json")
    # Should not raise
    json.dumps(data)
