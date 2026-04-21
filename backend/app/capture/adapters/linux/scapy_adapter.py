"""
Linux live capture adapter using scapy.

Requires:
  - scapy installed: pip install scapy
  - Root privileges or CAP_NET_RAW: sudo uvicorn ...

Packets are captured by scapy's AsyncSniffer in a background thread.
call_soon_threadsafe bridges scapy callbacks to the asyncio event loop.
Completed flows are pushed into an asyncio.Queue and served via next_event().
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.capture.base import CaptureAdapter
from app.contracts.schemas import NormalizedFlowEvent
from app.capture.adapters.linux.flow_aggregator import FlowAggregator
from app.capture.adapters.linux.feature_computer import compute_cicflow_features
from app.capture.adapters.linux.feature_computer_cic2023 import compute_cic2023_features
from app.capture.adapters.linux.flow_record import FlowRecord


PROTO_MAP = {6: "TCP", 17: "UDP", 1: "ICMP"}


class LinuxScapyAdapter(CaptureAdapter):
    mode = "linux_live"
    name = "Linux Scapy Live Capture"

    def __init__(self, interfaces: list[str] | str = "eth0", detection_mode: str = "simple") -> None:
        self._interfaces: list[str] = [interfaces] if isinstance(interfaces, str) else interfaces
        self._detection_mode = detection_mode
        self._queue: asyncio.Queue[NormalizedFlowEvent] = asyncio.Queue(maxsize=500)
        self._aggregator = FlowAggregator(on_flow_complete=self._on_flow_ready)
        self._sniffer = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Start scapy AsyncSniffer and flow reaper."""
        self._loop = asyncio.get_running_loop()
        await self._aggregator.start()

        try:
            from scapy.all import AsyncSniffer
        except ImportError as exc:
            raise RuntimeError(
                "scapy is not installed. Run: pip install scapy"
            ) from exc

        iface_arg = self._interfaces[0] if len(self._interfaces) == 1 else self._interfaces
        self._sniffer = AsyncSniffer(
            iface=iface_arg,
            filter="ip",
            prn=self._packet_callback,
            store=False,
        )
        self._sniffer.start()

    async def stop(self) -> None:
        """Stop sniffer and aggregator.
        join=False avoids blocking on socket.recv() in the scapy capture thread."""
        if self._sniffer is not None:
            try:
                self._sniffer.stop(join=False)
            except Exception:
                pass
            self._sniffer = None
        await self._aggregator.stop()

    def _packet_callback(self, pkt) -> None:
        """
        Called by scapy in its capture thread.
        ingest() is thread-safe (threading.Lock inside FlowAggregator) — call
        directly here so the asyncio event loop is NOT touched per-packet.
        This eliminates asyncio saturation under flood (2000+ pps).
        """
        self._aggregator.ingest(pkt)

    async def _on_flow_ready(self, record: FlowRecord) -> None:
        """Called by FlowAggregator when a flow is finalized."""
        try:
            raw_features = compute_cicflow_features(record)
        except Exception:
            return  # Skip malformed flows

        # Compute CIC2023 features only in advanced mode (saves CPU in simple mode)
        raw_features_cic2023 = None
        if self._detection_mode == "advanced":
            try:
                raw_features_cic2023 = compute_cic2023_features(record)
            except Exception:
                pass  # Missing secondary features → cascade will fallback to binary result

        protocol = PROTO_MAP.get(record.protocol, "OTHER")
        n_fwd = len(record.fwd_lengths)
        n_bwd = len(record.bwd_lengths)
        total_bytes = int(sum(record.fwd_lengths) + sum(record.bwd_lengths))
        duration_ms = max(int((record.last_time - record.start_time) * 1000), 1)

        event = NormalizedFlowEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            source=f"iface:{','.join(self._interfaces)}",
            direction="inbound",
            protocol=protocol,
            src_ip=record.src_ip,
            dst_ip=record.dst_ip,
            src_port=record.src_port,
            dst_port=record.dst_port,
            packet_count=max(n_fwd + n_bwd, 1),
            byte_count=max(total_bytes, 1),
            duration_ms=duration_ms,
            risk_hint=0.0,
            raw_features=raw_features,
            raw_features_cic2023=raw_features_cic2023,
        )

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Drop oldest event if queue is full under heavy traffic

    async def next_event(self) -> NormalizedFlowEvent:
        return await self._queue.get()
