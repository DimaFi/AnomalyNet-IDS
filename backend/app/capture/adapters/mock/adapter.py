from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from itertools import count, cycle
from random import Random

from app.capture.base import CaptureAdapter
from app.contracts.schemas import NormalizedFlowEvent


class MockCaptureAdapter(CaptureAdapter):
    mode = "mock"
    name = "Mock Flow Generator"

    def __init__(self) -> None:
        self._rng = Random(42)
        self._counter = count(1)
        self._directions = cycle(["inbound", "outbound", "lateral"])
        self._protocols = cycle(["TCP", "UDP", "ICMP", "OTHER"])
        self._sources = cycle(["sensor-lab", "gateway-edge", "device-cluster"])

    async def next_event(self) -> NormalizedFlowEvent:
        await asyncio.sleep(1.25)
        event_idx = next(self._counter)
        packet_count = self._rng.randint(8, 128)
        byte_count = packet_count * self._rng.randint(64, 900)
        duration_ms = self._rng.randint(80, 6000)
        risk_hint = round(min(0.98, byte_count / 70000 + packet_count / 160), 3)

        return NormalizedFlowEvent(
            event_id=f"flow-{event_idx:06d}",
            timestamp=datetime.now(timezone.utc),
            source=next(self._sources),
            direction=next(self._directions),
            protocol=next(self._protocols),
            src_ip=f"192.168.1.{10 + (event_idx % 20)}",
            dst_ip=f"10.0.0.{100 + (event_idx % 40)}",
            src_port=1024 + (event_idx % 40000),
            dst_port=[53, 80, 443, 1883, 502, 8080][event_idx % 6],
            packet_count=packet_count,
            byte_count=byte_count,
            duration_ms=duration_ms,
            risk_hint=risk_hint,
        )
