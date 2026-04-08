from __future__ import annotations

from app.contracts.schemas import FeatureVector, NormalizedFlowEvent
from app.preprocess.contracts import DEFAULT_CONTRACT_VERSION, DEFAULT_PROFILE_NAME


class MockPreprocessingPipeline:
    def transform(self, event: NormalizedFlowEvent) -> FeatureVector:
        packets_per_second = round(event.packet_count / max(event.duration_ms / 1000, 0.001), 3)
        bytes_per_second = round(event.byte_count / max(event.duration_ms / 1000, 0.001), 3)
        avg_packet_size = round(event.byte_count / max(event.packet_count, 1), 3)

        return FeatureVector(
            event_id=event.event_id,
            contract_version=DEFAULT_CONTRACT_VERSION,
            profile_name=DEFAULT_PROFILE_NAME,
            values={
                "Protocol": event.protocol,
                "Flow Duration": event.duration_ms,
                "Total Fwd Packet": event.packet_count,
                "Total Length of Fwd Packet": event.byte_count,
                "Flow Bytes/s": bytes_per_second,
                "Flow Packets/s": packets_per_second,
                "Average Packet Size": avg_packet_size,
                "Dst Port": event.dst_port,
                "Src Port": event.src_port,
                "Risk Hint": event.risk_hint,
            },
        )

