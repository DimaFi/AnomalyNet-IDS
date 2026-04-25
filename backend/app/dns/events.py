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


def dns_alert_to_pipeline_event(alert: dict) -> PipelineEvent:
    """Convert a DnsMonitor alert dict to a PipelineEvent for history storage.

    Flow-specific numeric fields are set to their minimum valid values (0/1)
    so Pydantic constraints pass; event_type="dns" lets downstream consumers
    skip flow-specific logic.
    """
    alert_type: str = alert["type"]          # "DGA_DOMAIN" | "DNS_TUNNELING"
    src_ip: str = alert.get("src_ip", "0.0.0.0")
    domain: str = alert.get("domain", "")
    entropy: float | None = alert.get("entropy")
    description: str = alert.get("description", "")
    ts = datetime.now(timezone.utc)
    eid = str(uuid4())

    flow_event = NormalizedFlowEvent(
        event_id=eid,
        timestamp=ts,
        source="dns_monitor",
        direction="outbound",
        protocol="DNS",
        src_ip=src_ip,
        dst_ip="0.0.0.0",
        src_port=0,
        dst_port=53,
        packet_count=1,
        byte_count=1,
        duration_ms=1,
        risk_hint=1.0,
        attack_class=alert_type,
    )

    # Normalise entropy to 0-1 (max theoretical entropy for 26+10 chars ≈ 5.0)
    score = round(min(entropy / 5.0, 1.0), 4) if entropy is not None else 1.0

    inference = InferenceResult(
        event_id=eid,
        label="anomaly",
        score=score,
        reason=alert_type,
        model_id="dns_monitor",
        attack_class=alert_type,
    )

    features = FeatureVector(
        event_id=eid,
        contract_version="dns_v1",
        profile_name="dns_monitor",
        values={},
        src_ip=src_ip,
    )

    alert_record = AlertRecord(
        alert_id=str(uuid4()),
        timestamp=ts,
        level="anomaly",
        title=f"DNS: {alert_type}",
        details=description,
        event_id=eid,
    )

    return PipelineEvent(
        event=flow_event,
        features=features,
        inference=inference,
        alert=alert_record,
        event_type="dns",
        priority="high",
        mitre=get_mitre(alert_type),
        metadata={
            "domain": domain,
            "entropy": entropy,
            "description": description,
            "transport": "UDP",
            "dns_alert_type": alert_type,
        },
    )
