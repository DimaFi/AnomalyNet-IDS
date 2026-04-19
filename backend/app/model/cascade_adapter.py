"""
Cascade model adapters for dual-mode detection.

CascadeSimpleAdapter   — Stage1 (binary) → Stage2 (multiclass, same 71 features)
CascadeAdvancedAdapter — Stage1 (binary) → Stage3 (multiclass, 46 CIC2023 features)
CascadeRoutedAdapter   — Stage1 (binary) → Stage2 or Stage3 based on protocol/port/IP routing:
    ICMP or UDP              → Stage3 (46-feat, flood/DoS)
    TCP + SSH/FTP flag       → Stage2 (71-feat, BruteForce)
    TCP + HTTP/HTTPS flag    → Stage2 (71-feat, WebAttack)
    private src_ip (RFC1918) → Stage3 (46-feat, IoT/Bot/Spoofing)
    public src_ip (default)  → Stage3 (46-feat, VPS/DoS/DDoS/Recon)

Logic:
  1. Run Stage1 (binary) on features.values
  2. If Stage1 says "normal" → return normal immediately (fast path)
  3. If Stage1 says attack → route to Stage2 or Stage3 → return multiclass result
"""
from __future__ import annotations

import ipaddress
from pathlib import Path

from app.contracts.schemas import FeatureVector, InferenceResult
from app.model.catboost_adapter import CatBoostModelAdapter


def _is_private_ip(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


class CascadeSimpleAdapter:
    """Stage1 (binary) → Stage2 (multiclass), both using the same 71 CICFlowMeter features."""

    def __init__(
        self,
        stage1_dir: Path | str,
        stage2_dir: Path | str,
        model_id: str,
        threshold: float = 0.70,
    ) -> None:
        self._stage1 = CatBoostModelAdapter(
            model_dir=stage1_dir,
            model_id=f"{model_id}/stage1",
            threshold=threshold,
        )
        self._stage2 = CatBoostModelAdapter(
            model_dir=stage2_dir,
            model_id=f"{model_id}/stage2",
            threshold=threshold,
        )
        self._model_id = model_id

    def infer(self, features: FeatureVector) -> InferenceResult:
        # Stage1: binary gate
        result1 = self._stage1.infer(features)

        if result1.label == "normal":
            # Benign — skip Stage2 entirely
            return result1

        # Stage2: multiclass classification (uses the same 71-feature values)
        result2 = self._stage2.infer(features)

        # If Stage2 is not confident (predicted Benign) — keep Stage1's detection
        # so that confirmed attacks are never silently downgraded to "normal"
        if result2.label == "normal":
            return InferenceResult(
                event_id=result1.event_id,
                label=result1.label,
                score=result1.score,
                reason=result1.reason + " [Stage2: низкая уверенность в классе]",
                model_id=self._model_id,
                attack_class=None,
            )

        return InferenceResult(
            event_id=result2.event_id,
            label=result2.label,
            score=result2.score,
            reason=result2.reason,
            model_id=self._model_id,
            attack_class=result2.attack_class,
        )


class CascadeAdvancedAdapter:
    """Stage1 (binary, 71 features) → Stage3 (multiclass, 46 CIC2023 features)."""

    def __init__(
        self,
        stage1_dir: Path | str,
        stage3_dir: Path | str,
        model_id: str,
        threshold: float = 0.70,
    ) -> None:
        self._stage1 = CatBoostModelAdapter(
            model_dir=stage1_dir,
            model_id=f"{model_id}/stage1",
            threshold=threshold,
        )
        self._stage3 = CatBoostModelAdapter(
            model_dir=stage3_dir,
            model_id=f"{model_id}/stage3",
            threshold=threshold,
        )
        self._model_id = model_id

    def infer(self, features: FeatureVector) -> InferenceResult:
        # Stage1: binary gate
        result1 = self._stage1.infer(features)

        if result1.label == "normal":
            return result1

        # Stage3: multiclass using secondary_values (46 CIC2023 features)
        if features.secondary_values is not None:
            sec_fv = FeatureVector(
                event_id=features.event_id,
                contract_version=features.contract_version,
                profile_name="catboost_iot_46_cic2023",
                values=features.secondary_values,
                secondary_values=None,
            )
            result3 = self._stage3.infer(sec_fv)
            # If Stage3 is not confident (returned normal) — fall back to Stage1 result
            if result3.label == "normal":
                return InferenceResult(
                    event_id=result1.event_id,
                    label=result1.label,
                    score=result1.score,
                    reason=result1.reason + " [Stage3: низкая уверенность в классе]",
                    model_id=self._model_id,
                    attack_class=None,
                )
            return InferenceResult(
                event_id=result3.event_id,
                label=result3.label,
                score=result3.score,
                reason=result3.reason,
                model_id=self._model_id,
                attack_class=result3.attack_class,
            )

        # Fallback: secondary features not available (e.g. flow too short)
        return InferenceResult(
            event_id=result1.event_id,
            label=result1.label,
            score=result1.score,
            reason=result1.reason + " [Stage3 skipped: no CIC2023 features]",
            model_id=self._model_id,
            attack_class=None,
        )


class CascadeRoutedAdapter:
    """
    Stage1 (binary, 71 features) → Stage2 or Stage3 based on routing rules.

    Stage2 (71-feat): handles TCP port-based attacks (BruteForce via SSH/FTP, WebAttack via HTTP/HTTPS)
    Stage3 (46-feat): handles floods (ICMP/UDP), IoT/Bot (private src_ip), VPS/DoS (public src_ip)

    Requires detection_mode=advanced so scapy computes secondary_values (46 CIC2023 features).
    """

    def __init__(
        self,
        stage1_dir: Path | str,
        stage2_dir: Path | str,
        stage3_dir: Path | str,
        model_id: str,
        threshold: float = 0.70,
    ) -> None:
        self._stage1 = CatBoostModelAdapter(
            model_dir=stage1_dir,
            model_id=f"{model_id}/stage1",
            threshold=threshold,
        )
        self._stage2 = CatBoostModelAdapter(
            model_dir=stage2_dir,
            model_id=f"{model_id}/stage2",
            threshold=threshold,
        )
        self._stage3 = CatBoostModelAdapter(
            model_dir=stage3_dir,
            model_id=f"{model_id}/stage3",
            threshold=threshold,
        )
        self._model_id = model_id

    def _route(self, features: FeatureVector) -> str:
        """Returns 'stage2' (71-feat) or 'stage3' (46-feat) based on traffic characteristics."""
        v = features.values

        # ICMP or UDP → Stage3 (flood attacks: DoS/DDoS)
        protocol = int(v.get("Protocol Type", 6))
        if (protocol == 1 or protocol == 17
                or int(v.get("ICMP", 0)) == 1
                or int(v.get("UDP", 0)) == 1):
            return "stage3"

        # TCP with known port flags → Stage2 (port-specific classifiers)
        if (int(v.get("SSH", 0)) or int(v.get("FTP", 0))
                or int(v.get("HTTP", 0)) or int(v.get("HTTPS", 0))):
            return "stage2"

        # private src_ip (RFC1918) → Stage3 (IoT: Bot, Spoofing)
        # public src_ip (default)  → Stage3 (VPS: DoS, DDoS, Recon)
        return "stage3"

    def infer(self, features: FeatureVector) -> InferenceResult:
        # Stage1: binary gate
        result1 = self._stage1.infer(features)
        if result1.label == "normal":
            return result1

        route = self._route(features)
        is_private = _is_private_ip(features.src_ip)
        route_label = (
            "Stage2/TCP" if route == "stage2"
            else ("Stage3/IoT" if is_private else "Stage3/VPS")
        )

        if route == "stage2":
            # Stage2: 71-feature multiclass (BruteForce/WebAttack)
            result2 = self._stage2.infer(features)
            if result2.label == "normal":
                return InferenceResult(
                    event_id=result1.event_id,
                    label=result1.label,
                    score=result1.score,
                    reason=result1.reason + f" [{route_label}: низкая уверенность в классе]",
                    model_id=self._model_id,
                    attack_class=None,
                )
            return InferenceResult(
                event_id=result2.event_id,
                label=result2.label,
                score=result2.score,
                reason=result2.reason,
                model_id=self._model_id,
                attack_class=result2.attack_class,
            )

        # Stage3: 46-feature multiclass (DoS/DDoS/Recon/Bot/Spoofing)
        if features.secondary_values is not None:
            sec_fv = FeatureVector(
                event_id=features.event_id,
                contract_version=features.contract_version,
                profile_name="catboost_iot_46_cic2023",
                values=features.secondary_values,
                secondary_values=None,
            )
            result3 = self._stage3.infer(sec_fv)
            if result3.label == "normal":
                return InferenceResult(
                    event_id=result1.event_id,
                    label=result1.label,
                    score=result1.score,
                    reason=result1.reason + f" [{route_label}: низкая уверенность в классе]",
                    model_id=self._model_id,
                    attack_class=None,
                )
            return InferenceResult(
                event_id=result3.event_id,
                label=result3.label,
                score=result3.score,
                reason=result3.reason,
                model_id=self._model_id,
                attack_class=result3.attack_class,
            )

        # Fallback: secondary_values not available (flow too short or simple mode)
        return InferenceResult(
            event_id=result1.event_id,
            label=result1.label,
            score=result1.score,
            reason=result1.reason + f" [{route_label}: no CIC2023 features, Stage1 fallback]",
            model_id=self._model_id,
            attack_class=None,
        )
