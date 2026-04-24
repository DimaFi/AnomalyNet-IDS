"""
Builtin wrapper: General Network Stage1 (binary) → BaseModel.

Бинарный CatBoost детектор, обученный на CICIDS 2017 (PC/home network traffic).
Использует те же 71 CICFlowMeter признаков что и IoT Stage1, но с другими медианами.
"""
from __future__ import annotations

from pathlib import Path

from app.plugins.base_model import BaseModel
from app.plugins.contracts import PluginFeatureVector, PluginVerdict
from app.plugins.builtin.model_stage1 import _to_feature_vector, _to_plugin_verdict


class BuiltinGeneralStage1Model(BaseModel):
    """
    General Network Stage1: бинарный CatBoost (71 CICFlowMeter признаков, CICIDS 2017).
    Предназначен для ПК, смартфонов и общесетевого трафика — низкий FPR на не-IoT устройствах.
    """

    def __init__(self, model_dir: str | Path, threshold: float = 0.70) -> None:
        self._model_dir = Path(model_dir)
        self._threshold = threshold
        self._adapter   = None

    def get_name(self) -> str:
        return "builtin_general_stage1"

    def get_description(self) -> str:
        return "General Network Stage1: бинарный CatBoost (71 признаков, CICIDS 2017)"

    def get_version(self) -> str:
        return "1.0.0"

    def get_accepted_schema_ids(self) -> list[str]:
        return ["cicflowmeter_71_general"]

    def get_output_classes(self) -> list[str]:
        return ["Benign", "Attack"]

    def on_load(self) -> None:
        from app.model.catboost_adapter import CatBoostModelAdapter
        self._adapter = CatBoostModelAdapter(
            model_dir=self._model_dir,
            model_id="builtin_general_stage1",
            threshold=self._threshold,
        )

    def on_unload(self) -> None:
        self._adapter = None

    def predict(self, features: PluginFeatureVector) -> PluginVerdict:
        if self._adapter is None:
            raise RuntimeError("BuiltinGeneralStage1Model не загружен.")

        ok, reason = self.check_compatibility(features.schema_id)
        if not ok:
            raise ValueError(reason)

        fv = _to_feature_vector(features)
        result = self._adapter.infer(fv)
        return _to_plugin_verdict(result, stage="stage1")
