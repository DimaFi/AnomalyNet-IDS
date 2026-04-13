"""
Cascade model adapters for dual-mode detection.

CascadeSimpleAdapter  — Stage1 (binary) → Stage2 (multiclass, same 71 features)
CascadeAdvancedAdapter — Stage1 (binary) → Stage3 (multiclass, 46 CIC2023 features)

Logic:
  1. Run Stage1 (binary) on features.values
  2. If Stage1 says "normal" → return normal immediately (fast path)
  3. If Stage1 says attack → run secondary model → return multiclass result with attack_class
"""
from __future__ import annotations

from pathlib import Path

from app.contracts.schemas import FeatureVector, InferenceResult
from app.model.catboost_adapter import CatBoostModelAdapter


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
        # Override model_id to reflect cascade
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
