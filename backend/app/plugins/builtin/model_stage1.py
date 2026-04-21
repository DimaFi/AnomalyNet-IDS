"""
Builtin wrapper: CatBoostModelAdapter (binary) → BaseModel.

Обёртывает бинарный CatBoostModelAdapter (Stage1 gate) для plugin pipeline.
Принимает PluginFeatureVector со schema_id="cicflowmeter_71",
возвращает PluginVerdict.
"""
from __future__ import annotations

from pathlib import Path

from app.plugins.base_model import BaseModel
from app.plugins.contracts import PluginFeatureVector, PluginVerdict


class BuiltinStage1Model(BaseModel):
    """
    Wraps CatBoostModelAdapter (model.cbm, binary) для plugin pipeline.

    model_dir: папка с model.cbm (stage1_v2_cl/models/catboost)
    threshold: порог срабатывания (default 0.70)
    """

    def __init__(self, model_dir: str | Path, threshold: float = 0.70) -> None:
        self._model_dir = Path(model_dir)
        self._threshold = threshold
        self._adapter   = None

    # ── BaseModel interface ────────────────────────────────────────────────────

    def get_name(self) -> str:
        return "builtin_stage1_binary"

    def get_description(self) -> str:
        return "Stage1: бинарный CatBoost детектор (71 CICFlowMeter признаков, IoT-DIAD 2024)"

    def get_version(self) -> str:
        return "1.0.0"

    def get_accepted_schema_ids(self) -> list[str]:
        return ["cicflowmeter_71"]

    def get_output_classes(self) -> list[str]:
        return ["Benign", "Attack"]

    def on_load(self) -> None:
        from app.model.catboost_adapter import CatBoostModelAdapter
        self._adapter = CatBoostModelAdapter(
            model_dir=self._model_dir,
            model_id="builtin_stage1_binary",
            threshold=self._threshold,
        )

    def on_unload(self) -> None:
        self._adapter = None

    def predict(self, features: PluginFeatureVector) -> PluginVerdict:
        if self._adapter is None:
            raise RuntimeError(
                "BuiltinStage1Model не загружен. "
                "Вызови on_load() или зарегистрируй в PluginRegistry."
            )

        ok, reason = self.check_compatibility(features.schema_id)
        if not ok:
            raise ValueError(reason)

        fv = _to_feature_vector(features)
        result = self._adapter.infer(fv)
        return _to_plugin_verdict(result, stage="stage1")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_feature_vector(pfv: PluginFeatureVector):
    """Конвертирует PluginFeatureVector(list) → FeatureVector(dict) для существующих адаптеров."""
    from app.contracts.schemas import FeatureVector
    values = dict(zip(pfv.feature_names, (float(v) for v in pfv.features)))
    return FeatureVector(
        event_id=pfv.meta.get("event_id", ""),
        contract_version="feature-contract.v1",
        profile_name=pfv.schema_id,
        values=values,
        src_ip=pfv.meta.get("src_ip"),
    )


def _to_plugin_verdict(result, stage: str) -> PluginVerdict:
    """Конвертирует InferenceResult → PluginVerdict."""
    return PluginVerdict(
        score=result.score,
        verdict=result.label,
        attack_class=result.attack_class,
        model_name=result.model_id,
        stage=stage,
        reason=result.reason,
    )
