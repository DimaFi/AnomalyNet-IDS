"""
Computes all 71 CICFlowMeter features from a finalized FlowRecord.
Feature names exactly match feature_contract.json used during model training.
"""

from __future__ import annotations

import math
from typing import Any

from app.capture.adapters.linux.flow_record import FlowRecord


def _safe_stats(values: list[float]) -> dict[str, float]:
    """Mean, std, max, min — returns zeros for empty lists."""
    if not values:
        return {"mean": 0.0, "std": 0.0, "max": 0.0, "min": 0.0}
    n = len(values)
    total = sum(values)
    mean = total / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return {
        "mean": mean,
        "std": math.sqrt(variance),
        "max": max(values),
        "min": min(values),
    }


def _iat_stats(timestamps: list[float]) -> dict[str, float]:
    """Inter-arrival time stats in microseconds."""
    if len(timestamps) < 2:
        return {"total": 0.0, "mean": 0.0, "std": 0.0, "max": 0.0, "min": 0.0}
    sorted_ts = sorted(timestamps)
    iats_us = [(sorted_ts[i + 1] - sorted_ts[i]) * 1e6 for i in range(len(sorted_ts) - 1)]
    stats = _safe_stats(iats_us)
    return {
        "total": sum(iats_us),
        "mean": stats["mean"],
        "std": stats["std"],
        "max": stats["max"],
        "min": stats["min"],
    }


def _count_flag(flag_list: list[int], bit: int) -> float:
    return float(sum(1 for f in flag_list if f & bit))


# TCP flag bit masks
FIN = 0x01
SYN = 0x02
RST = 0x04
PSH = 0x08
ACK = 0x10
URG = 0x20
ECE = 0x40
CWR = 0x80


def compute_cicflow_features(record: FlowRecord) -> dict[str, float]:
    """
    Returns a dict keyed by exact feature names from feature_contract.json.
    All 71 features are always present; missing data yields 0.0.
    """
    record.finalize_active_period()

    fwd = record.fwd_lengths
    bwd = record.bwd_lengths
    all_pkts = fwd + bwd

    duration_us = max((record.last_time - record.start_time) * 1e6, 1.0)
    duration_s  = duration_us / 1e6

    n_fwd = len(fwd)
    n_bwd = len(bwd)
    n_all = n_fwd + n_bwd

    total_fwd_bytes = sum(fwd)
    total_bwd_bytes = sum(bwd)
    total_bytes = total_fwd_bytes + total_bwd_bytes

    fwd_stats  = _safe_stats(fwd)
    bwd_stats  = _safe_stats(bwd)
    all_stats  = _safe_stats(all_pkts)
    fwd_iat    = _iat_stats(record.fwd_times)
    bwd_iat    = _iat_stats(record.bwd_times)
    flow_iat   = _iat_stats(record.fwd_times + record.bwd_times)
    act_stats  = _safe_stats(record.active_periods)
    idle_stats = _safe_stats(record.idle_periods)

    all_flags = record.fwd_flags + record.bwd_flags
    all_lens  = all_pkts

    variance = sum((v - all_stats["mean"]) ** 2 for v in all_lens) / max(n_all, 1)

    return {
        "Protocol":                    float(record.protocol),
        "Flow Duration":               duration_us,
        "Total Fwd Packet":            float(n_fwd),
        "Total Bwd packets":           float(n_bwd),
        "Total Length of Fwd Packet":  total_fwd_bytes,
        "Total Length of Bwd Packet":  total_bwd_bytes,
        "Fwd Packet Length Max":       fwd_stats["max"],
        "Fwd Packet Length Min":       fwd_stats["min"],
        "Fwd Packet Length Mean":      fwd_stats["mean"],
        "Fwd Packet Length Std":       fwd_stats["std"],
        "Bwd Packet Length Max":       bwd_stats["max"],
        "Bwd Packet Length Min":       bwd_stats["min"],
        "Bwd Packet Length Mean":      bwd_stats["mean"],
        "Bwd Packet Length Std":       bwd_stats["std"],
        "Flow Bytes/s":                total_bytes / duration_s,
        "Flow Packets/s":              n_all / duration_s,
        "Flow IAT Mean":               flow_iat["mean"],
        "Flow IAT Std":                flow_iat["std"],
        "Flow IAT Max":                flow_iat["max"],
        "Flow IAT Min":                flow_iat["min"],
        "Fwd IAT Total":               fwd_iat["total"],
        "Fwd IAT Mean":                fwd_iat["mean"],
        "Fwd IAT Std":                 fwd_iat["std"],
        "Fwd IAT Max":                 fwd_iat["max"],
        "Fwd IAT Min":                 fwd_iat["min"],
        "Bwd IAT Total":               bwd_iat["total"],
        "Bwd IAT Mean":                bwd_iat["mean"],
        "Bwd IAT Std":                 bwd_iat["std"],
        "Bwd IAT Max":                 bwd_iat["max"],
        "Bwd IAT Min":                 bwd_iat["min"],
        "Fwd PSH Flags":               _count_flag(record.fwd_flags, PSH),
        "Bwd PSH Flags":               _count_flag(record.bwd_flags, PSH),
        "Fwd URG Flags":               _count_flag(record.fwd_flags, URG),
        "Bwd URG Flags":               _count_flag(record.bwd_flags, URG),
        "Fwd Header Length":           float(sum(record.fwd_header_lengths)),
        "Bwd Header Length":           float(sum(record.bwd_header_lengths)),
        "Fwd Packets/s":               n_fwd / duration_s,
        "Bwd Packets/s":               n_bwd / duration_s,
        "Packet Length Min":           all_stats["min"],
        "Packet Length Max":           all_stats["max"],
        "Packet Length Mean":          all_stats["mean"],
        "Packet Length Std":           all_stats["std"],
        "Packet Length Variance":      variance,
        "FIN Flag Count":              _count_flag(all_flags, FIN),
        "SYN Flag Count":              _count_flag(all_flags, SYN),
        "RST Flag Count":              _count_flag(all_flags, RST),
        "PSH Flag Count":              _count_flag(all_flags, PSH),
        "ACK Flag Count":              _count_flag(all_flags, ACK),
        "URG Flag Count":              _count_flag(all_flags, URG),
        "CWR Flag Count":              _count_flag(all_flags, CWR),
        "ECE Flag Count":              _count_flag(all_flags, ECE),
        "Down/Up Ratio":               n_bwd / max(n_fwd, 1),
        "Average Packet Size":         total_bytes / max(n_all, 1),
        "Fwd Segment Size Avg":        fwd_stats["mean"],
        "Bwd Segment Size Avg":        bwd_stats["mean"],
        "Subflow Fwd Packets":         float(n_fwd),
        "Subflow Fwd Bytes":           total_fwd_bytes,
        "Subflow Bwd Packets":         float(n_bwd),
        "Subflow Bwd Bytes":           total_bwd_bytes,
        "FWD Init Win Bytes":          float(record.fwd_init_win),
        "Bwd Init Win Bytes":          float(record.bwd_init_win),
        "Fwd Act Data Pkts":           float(sum(1 for l in fwd if l > 0)),
        "Fwd Seg Size Min":            fwd_stats["min"],
        "Active Mean":                 act_stats["mean"],
        "Active Std":                  act_stats["std"],
        "Active Max":                  act_stats["max"],
        "Active Min":                  act_stats["min"],
        "Idle Mean":                   idle_stats["mean"],
        "Idle Std":                    idle_stats["std"],
        "Idle Max":                    idle_stats["max"],
        "Idle Min":                    idle_stats["min"],
    }
