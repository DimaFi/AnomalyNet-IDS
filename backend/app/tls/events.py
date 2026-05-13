"""
TLS alert → PipelineEvent converter.

Platform-independent — works with alert dicts from TLSMonitor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.contracts.schemas import (
    AlertRecord,
    FeatureVector,
    InferenceResult,
    NormalizedFlowEvent,
    PipelineEvent,
)
from app.mitre.mapping import get_mitre
from app.security.ja4_reputation import lookup_ja4_reputation


def tls_alert_to_pipeline_event(alert: dict) -> PipelineEvent:
    """Convert a TLSMonitor alert dict to a PipelineEvent for history storage.

    Mirrors dns_alert_to_pipeline_event() pattern:
    - event_type = "tls"
    - protocol = "TLS"
    - priority = "medium"  (TLS is a weak signal, not a definitive attack)
    - mitre = None         (not added at MVP stage)
    - metadata contains ja4, sni, alpn, tls_version, etc.
    """
    alert_type: str = alert["type"]   # "NEW_TLS_FINGERPRINT" | "TOO_MANY_TLS_FINGERPRINTS"
    src_ip: str = alert.get("src_ip", "0.0.0.0")
    dst_ip: str = alert.get("dst_ip", "0.0.0.0")
    dst_port: int = alert.get("dst_port", 0)
    description: str = alert.get("description", "")
    unique_count: int = alert.get("unique_count", 1)
    fp: dict = alert.get("fingerprint", {})

    ts = datetime.now(timezone.utc)
    eid = str(uuid4())

    flow_event = NormalizedFlowEvent(
        event_id=eid,
        timestamp=ts,
        source="tls_monitor",
        direction="outbound",
        protocol="TLS",
        src_ip=src_ip,
        dst_ip=dst_ip,
        src_port=0,
        dst_port=max(dst_port, 0),
        packet_count=1,
        byte_count=1,
        duration_ms=1,
        risk_hint=0.5,
        attack_class=alert_type,
    )

    # Score: NEW fingerprint → 0.5 (medium confidence), TOO_MANY → 0.7 (higher concern)
    score = 0.7 if alert_type == "TOO_MANY_TLS_FINGERPRINTS" else 0.5

    # JA4 reputation check — boosts score if fingerprint is in known-bad DB
    ja4_str = fp.get("ja4", "")
    reputation = lookup_ja4_reputation(ja4_str)
    if reputation:
        score = min(1.0, score + reputation.get("score_boost", 0.0))

    inference = InferenceResult(
        event_id=eid,
        label="warning",
        score=round(score, 4),
        reason=alert_type,
        model_id="tls_monitor",
        attack_class=alert_type,
    )

    features = FeatureVector(
        event_id=eid,
        contract_version="tls_v1",
        profile_name="tls_monitor",
        values={},
        src_ip=src_ip,
    )

    alert_record = AlertRecord(
        alert_id=str(uuid4()),
        timestamp=ts,
        level="warning",
        title=f"TLS: {alert_type}",
        details=description,
        event_id=eid,
    )

    # Priority: reputation hit → high, TOO_MANY → high, default → medium
    if reputation and reputation.get("severity") in ("critical", "high"):
        priority = "high"
    elif alert_type == "TOO_MANY_TLS_FINGERPRINTS":
        priority = "high"
    else:
        priority = "medium"

    metadata: dict = {
        "ja4":          ja4_str,
        "ja4_legacy":   fp.get("ja4_legacy", ""),
        "ja4_raw":      fp.get("ja4_raw", ""),
        "ja4_source":   fp.get("ja4_source", ""),
        "ja4_version":  fp.get("ja4_version", ""),
        "sni":          fp.get("sni", ""),
        "alpn":         fp.get("alpn", ""),
        "tls_version":  fp.get("tls_version", ""),
        "cipher_count": fp.get("cipher_count", 0),
        "ext_count":    fp.get("ext_count", 0),
        "reason":       description,
        "tls_alert_type": alert_type,
        "unique_count": unique_count,
    }
    if reputation:
        metadata["ja4_reputation"] = {
            "label":       reputation.get("label", ""),
            "severity":    reputation.get("severity", ""),
            "description": reputation.get("description", ""),
            "source":      reputation.get("source", ""),
        }

    return PipelineEvent(
        event=flow_event,
        features=features,
        inference=inference,
        alert=alert_record,
        event_type="tls",
        priority=priority,
        mitre=get_mitre(alert_type),
        metadata=metadata,
    )
