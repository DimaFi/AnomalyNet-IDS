"""
FlowRecord — per-flow state accumulator.

Tracks all packet-level data needed to compute 71 CICFlowMeter features
when the flow is finalized (TCP FIN/RST or idle timeout).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Gap between packets > this value (seconds) → start a new active/idle period
ACTIVITY_TIMEOUT_S: float = 5.0


@dataclass
class FlowRecord:
    # 5-tuple
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int  # 6=TCP, 17=UDP, 1=ICMP

    # Timing (monotonic seconds)
    start_time: float
    last_time: float

    # Per-direction payload lengths (bytes, NOT including headers)
    fwd_lengths: list[float] = field(default_factory=list)  # src→dst
    bwd_lengths: list[float] = field(default_factory=list)  # dst→src

    # Per-direction timestamps for IAT computation
    fwd_times: list[float] = field(default_factory=list)
    bwd_times: list[float] = field(default_factory=list)

    # TCP flag bytes per packet (per direction)
    fwd_flags: list[int] = field(default_factory=list)
    bwd_flags: list[int] = field(default_factory=list)

    # TCP initial window sizes (first packet of each direction)
    fwd_init_win: int = 0
    bwd_init_win: int = 0
    _fwd_init_win_set: bool = field(default=False, repr=False)
    _bwd_init_win_set: bool = field(default=False, repr=False)

    # Header lengths per direction (IP header + TCP/UDP header)
    fwd_header_lengths: list[int] = field(default_factory=list)
    bwd_header_lengths: list[int] = field(default_factory=list)

    # Active/Idle tracking
    active_periods: list[float] = field(default_factory=list)  # µs
    idle_periods: list[float] = field(default_factory=list)    # µs
    _active_start: float = field(default=0.0, repr=False)

    # TCP FIN/RST signal
    closing: bool = False

    def add_packet(
        self,
        ts: float,
        payload_len: int,
        header_len: int,
        is_fwd: bool,
        tcp_flags: int = 0,
        tcp_win: int = 0,
    ) -> None:
        gap = ts - self.last_time

        # Active/Idle period tracking
        if self.last_time > 0 and gap > ACTIVITY_TIMEOUT_S:
            # Close current active period, record idle gap
            active_dur = (self.last_time - self._active_start) * 1e6
            if active_dur > 0:
                self.active_periods.append(active_dur)
            self.idle_periods.append(gap * 1e6)
            self._active_start = ts

        self.last_time = ts

        if is_fwd:
            self.fwd_lengths.append(float(payload_len))
            self.fwd_times.append(ts)
            self.fwd_flags.append(tcp_flags)
            self.fwd_header_lengths.append(header_len)
            if not self._fwd_init_win_set and tcp_win > 0:
                self.fwd_init_win = tcp_win
                self._fwd_init_win_set = True
        else:
            self.bwd_lengths.append(float(payload_len))
            self.bwd_times.append(ts)
            self.bwd_flags.append(tcp_flags)
            self.bwd_header_lengths.append(header_len)
            if not self._bwd_init_win_set and tcp_win > 0:
                self.bwd_init_win = tcp_win
                self._bwd_init_win_set = True

        # Mark closing if FIN or RST
        if tcp_flags & 0x01 or tcp_flags & 0x04:  # FIN=0x01, RST=0x04
            self.closing = True

    def finalize_active_period(self) -> None:
        """Called when flow expires — closes the last active period."""
        active_dur = (self.last_time - self._active_start) * 1e6
        if active_dur > 0:
            self.active_periods.append(active_dur)
