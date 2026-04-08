"""
Computes 46 CIC IoT 2023 features from a finalized FlowRecord.

These features are used by the stage3_cic2023 model (Advanced detection mode).
They are different from the 71 CICFlowMeter features used by stage1/stage2.

Feature names must exactly match those in stage3_cic2023/artifacts/feature_contract.json.
Note: "Magnitue" is intentionally misspelled — it matches the original dataset.
"""

from __future__ import annotations

import math
from typing import Any

from app.capture.adapters.linux.flow_record import FlowRecord


# TCP flag bit masks (same as feature_computer.py)
FIN = 0x01
SYN = 0x02
RST = 0x04
PSH = 0x08
ACK = 0x10
URG = 0x20
ECE = 0x40
CWR = 0x80

# Port → application protocol mappings
_HTTP_PORTS   = frozenset({80, 8080, 8000, 8008})
_HTTPS_PORTS  = frozenset({443, 8443})
_DNS_PORTS    = frozenset({53})
_TELNET_PORTS = frozenset({23})
_SMTP_PORTS   = frozenset({25, 587, 465})
_SSH_PORTS    = frozenset({22})
_IRC_PORTS    = frozenset({6667, 6668, 6669})
_DHCP_PORTS   = frozenset({67, 68})


def _count_flag(flags: list[int], bit: int) -> float:
    return float(sum(1 for f in flags if f & bit))


def _safe_stats(values: list[float]) -> tuple[float, float, float, float, float]:
    """Returns (total, min, max, mean, std). All zeros for empty list."""
    if not values:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    n = len(values)
    s = sum(values)
    mean = s / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return s, min(values), max(values), mean, math.sqrt(variance)


def compute_cic2023_features(record: FlowRecord) -> dict[str, float]:
    """
    Returns a dict with the 46 CIC IoT 2023 feature names.
    All features are always present; missing data yields 0.0.
    """
    record.finalize_active_period()

    fwd = record.fwd_lengths
    bwd = record.bwd_lengths
    all_pkts = fwd + bwd

    n_fwd = len(fwd)
    n_bwd = len(bwd)
    n_all = n_fwd + n_bwd

    duration_s = max(record.last_time - record.start_time, 1e-9)

    all_flags = record.fwd_flags + record.bwd_flags
    all_headers = record.fwd_header_lengths + record.bwd_header_lengths

    tot_sum, pkt_min, pkt_max, pkt_avg, pkt_std = _safe_stats(all_pkts)
    _, _, _, fwd_mean, fwd_std = _safe_stats(fwd)
    _, _, _, bwd_mean, bwd_std = _safe_stats(bwd)

    header_avg = sum(all_headers) / max(n_all, 1)

    # IAT — mean inter-arrival time (microseconds)
    all_times = sorted(record.fwd_times + record.bwd_times)
    if len(all_times) >= 2:
        iats_us = [(all_times[i + 1] - all_times[i]) * 1e6
                   for i in range(len(all_times) - 1)]
        iat_mean = sum(iats_us) / len(iats_us)
    else:
        iat_mean = 0.0

    # Magnitude: sqrt(fwd_mean² + bwd_mean²)
    magnitude = math.sqrt(fwd_mean ** 2 + bwd_mean ** 2)

    # Radius: sqrt((fwd_var + bwd_var) / 2)
    fwd_var = fwd_std ** 2
    bwd_var = bwd_std ** 2
    radius = math.sqrt((fwd_var + bwd_var) / 2.0)

    # Covariance between fwd and bwd packet lengths
    if fwd and bwd:
        n_both = min(len(fwd), len(bwd))
        covariance = sum(
            (fwd[i] - fwd_mean) * (bwd[i] - bwd_mean)
            for i in range(n_both)
        ) / max(n_both, 1)
    else:
        covariance = 0.0

    # Variance of all packet lengths
    variance = pkt_std ** 2

    # Weight — packets per second (common definition in IoT papers)
    weight = n_all / duration_s

    # Port-based protocol flags (binary: 1.0 if the flow uses this protocol)
    ports = {record.src_port, record.dst_port}

    return {
        "flow_duration":   duration_s,
        "Header_Length":   header_avg,
        "Protocol Type":   float(record.protocol),
        "Duration":        duration_s,
        "Rate":            n_all / duration_s,
        "Srate":           n_fwd / duration_s,
        "Drate":           n_bwd / duration_s,
        # TCP flag counts (all directions)
        "fin_flag_number": _count_flag(all_flags, FIN),
        "syn_flag_number": _count_flag(all_flags, SYN),
        "rst_flag_number": _count_flag(all_flags, RST),
        "psh_flag_number": _count_flag(all_flags, PSH),
        "ack_flag_number": _count_flag(all_flags, ACK),
        "ece_flag_number": _count_flag(all_flags, ECE),
        "cwr_flag_number": _count_flag(all_flags, CWR),
        # Duplicate flag counts (different names, same values — as in original dataset)
        "ack_count":       _count_flag(all_flags, ACK),
        "syn_count":       _count_flag(all_flags, SYN),
        "fin_count":       _count_flag(all_flags, FIN),
        "urg_count":       _count_flag(all_flags, URG),
        "rst_count":       _count_flag(all_flags, RST),
        # Application protocol flags (inferred from port numbers)
        "HTTP":            1.0 if ports & _HTTP_PORTS   else 0.0,
        "HTTPS":           1.0 if ports & _HTTPS_PORTS  else 0.0,
        "DNS":             1.0 if ports & _DNS_PORTS    else 0.0,
        "Telnet":          1.0 if ports & _TELNET_PORTS else 0.0,
        "SMTP":            1.0 if ports & _SMTP_PORTS   else 0.0,
        "SSH":             1.0 if ports & _SSH_PORTS    else 0.0,
        "IRC":             1.0 if ports & _IRC_PORTS    else 0.0,
        # Transport / network protocol flags
        "TCP":             1.0 if record.protocol == 6  else 0.0,
        "UDP":             1.0 if record.protocol == 17 else 0.0,
        "DHCP":            1.0 if ports & _DHCP_PORTS   else 0.0,
        "ARP":             0.0,   # ARP is layer-2; not available from IP-level capture
        "ICMP":            1.0 if record.protocol == 1  else 0.0,
        "IPv":             4.0,   # scapy IP layer → always IPv4 here
        "LLC":             0.0,   # LLC is layer-2; not available from IP-level capture
        # Packet length statistics
        "Tot sum":         tot_sum,
        "Min":             pkt_min,
        "Max":             pkt_max,
        "AVG":             pkt_avg,
        "Std":             pkt_std,
        "Tot size":        tot_sum,   # same as Tot sum in original dataset
        # Timing
        "IAT":             iat_mean,
        "Number":          float(n_all),
        # Correlation / statistical features
        "Magnitue":        magnitude,   # intentional typo — matches dataset column name
        "Radius":          radius,
        "Covariance":      covariance,
        "Variance":        variance,
        "Weight":          weight,
    }
