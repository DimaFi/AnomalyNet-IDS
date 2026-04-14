"""
FlowAggregator — aggregates raw packets into bidirectional network flows.

Uses a canonical 5-tuple key so packets from both directions end up in the
same FlowRecord.  When a flow expires (TCP FIN/RST or idle timeout), the
on_flow_complete callback is called with the completed FlowRecord.

Thread-safety model
-------------------
_process_packet() (called directly from the scapy capture thread) and
_expire_flow() / _reaper_loop() (called from the asyncio event loop) both
touch self._flows / self._closing.  A plain threading.Lock protects those
dicts so no data is lost and no asyncio overhead is paid per-packet.

Key invariant: the lock is *never* held across an await — we pop the record
first, release the lock, then call the async callback.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Callable, Awaitable

from app.capture.adapters.linux.flow_record import FlowRecord

# Maximum simultaneous tracked flows (DoS / SYN-flood protection)
# When cap is reached, new flows are DROPPED (not evicted) — O(1), no CPU spike
MAX_FLOWS = 10_000
# Flow is expired if last packet was more than this many seconds ago
FLOW_TIMEOUT_S: float = 60.0
# How often the reaper wakes up to sweep expired flows
REAPER_INTERVAL_S: float = 5.0
# Grace period after FIN/RST before finalizing (seconds)
FIN_GRACE_S: float = 2.0


class FlowAggregator:
    def __init__(
        self,
        on_flow_complete: Callable[[FlowRecord], Awaitable[None]],
        flow_timeout: float = FLOW_TIMEOUT_S,
        activity_timeout: float = 5.0,
    ) -> None:
        self._flows: dict[tuple, FlowRecord] = {}
        # Maps flow key → timestamp when FIN/RST was seen (for grace period)
        self._closing: dict[tuple, float] = {}
        self._lock = threading.Lock()          # protects _flows and _closing
        self._on_flow_complete = on_flow_complete
        self._flow_timeout = flow_timeout
        self._reaper_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def stop(self) -> None:
        if self._reaper_task:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
        with self._lock:
            self._flows.clear()
            self._closing.clear()

    def ingest(self, pkt) -> None:
        """
        Called DIRECTLY from the scapy capture thread (not via call_soon_threadsafe).
        Must be fully synchronous.  threading.Lock makes _flows access safe.
        """
        try:
            self._process_packet(pkt)
        except Exception:
            pass  # Never crash the sniffer thread

    def _process_packet(self, pkt) -> None:
        # Lazy import scapy layers to avoid import-time cost
        try:
            from scapy.layers.inet import IP, TCP, UDP, ICMP
        except ImportError:
            return

        if IP not in pkt:
            return

        ip = pkt[IP]
        src_ip: str = ip.src
        dst_ip: str = ip.dst
        proto: int  = ip.proto  # 6=TCP, 17=UDP, 1=ICMP

        src_port = 0
        dst_port = 0
        tcp_flags = 0
        tcp_win   = 0

        if proto == 6 and TCP in pkt:
            tcp = pkt[TCP]
            src_port  = tcp.sport
            dst_port  = tcp.dport
            tcp_flags = int(tcp.flags)
            tcp_win   = tcp.window
        elif proto == 17 and UDP in pkt:
            udp = pkt[UDP]
            src_port = udp.sport
            dst_port = udp.dport

        # IP header length (in bytes)
        ip_hdr_len = ip.ihl * 4 if hasattr(ip, "ihl") else 20
        # Transport header length
        if proto == 6 and TCP in pkt:
            tcp = pkt[TCP]
            trans_hdr_len = tcp.dataofs * 4 if hasattr(tcp, "dataofs") else 20
        elif proto == 17:
            trans_hdr_len = 8  # UDP fixed header
        else:
            trans_hdr_len = 0
        header_len = ip_hdr_len + trans_hdr_len

        # Payload length = IP total length - all headers
        ip_total = ip.len if hasattr(ip, "len") and ip.len else len(pkt[IP])
        payload_len = max(ip_total - header_len, 0)

        # Canonical key: ensures same FlowRecord for both directions
        key = self._canonical_key(src_ip, dst_ip, src_port, dst_port, proto)
        ts = time.monotonic()

        schedule_fin = False

        with self._lock:
            if key not in self._flows:
                # Enforce MAX_FLOWS cap: DROP new flows when full (O(1), prevents CPU spike)
                if len(self._flows) >= MAX_FLOWS:
                    return

                record = FlowRecord(
                    src_ip=src_ip,
                    dst_ip=dst_ip,
                    src_port=src_port,
                    dst_port=dst_port,
                    protocol=proto,
                    start_time=ts,
                    last_time=ts,
                    _active_start=ts,
                )
                self._flows[key] = record

            record = self._flows[key]
            is_fwd = (record.src_ip == src_ip and record.src_port == src_port)
            record.add_packet(
                ts=ts,
                payload_len=payload_len,
                header_len=header_len,
                is_fwd=is_fwd,
                tcp_flags=tcp_flags,
                tcp_win=tcp_win,
            )

            # Mark for FIN/RST grace scheduling (outside the lock)
            if record.closing and key not in self._closing:
                self._closing[key] = ts
                schedule_fin = True

        # Schedule FIN/RST grace expiry — done OUTSIDE lock so we don't hold
        # it across the (thread-safe but potentially contended) call_soon_threadsafe
        if schedule_fin and self._loop:
            self._loop.call_soon_threadsafe(
                self._loop.call_later,
                FIN_GRACE_S,
                lambda k=key: asyncio.ensure_future(self._expire_flow(k)),
            )

    @staticmethod
    def _canonical_key(
        src_ip: str, dst_ip: str, src_port: int, dst_port: int, proto: int
    ) -> tuple:
        if (src_ip, src_port) < (dst_ip, dst_port):
            return (proto, src_ip, src_port, dst_ip, dst_port)
        return (proto, dst_ip, dst_port, src_ip, src_port)

    async def _expire_flow(self, key: tuple) -> None:
        # Pop under lock, then call async callback WITHOUT holding lock
        with self._lock:
            record = self._flows.pop(key, None)
            self._closing.pop(key, None)
        if record:
            await self._on_flow_complete(record)

    async def _reaper_loop(self) -> None:
        while True:
            await asyncio.sleep(REAPER_INTERVAL_S)
            now = time.monotonic()
            with self._lock:
                expired = [
                    k for k, r in self._flows.items()
                    if (now - r.last_time) >= self._flow_timeout
                ]
            for key in expired:
                await self._expire_flow(key)
