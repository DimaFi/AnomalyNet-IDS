"""
Builtin wrapper: CatBoostModelAdapter (multiclass, 71 features) → BaseModel.

Обёртывает многоклассовый CatBoostModelAdapter Stage2 (model_mc.cbm, 71 признак).
Принимает PluginFeatureVector со schema_id="cicflowmeter_71",
возвращает PluginVerdict с attack_class.
"""
from __future__ import annotations

from pathlib import Path

from app.plugins.base_model import BaseModel
from app.plugins.contracts import PluginFeatureVector, PluginVerdict
from app.plugins.builtin.model_stage1 import _to_feature_vector, _to_plugin_verdict


class BuiltinStage2Model(BaseModel):
    """
    Wraps CatBoostModelAdapter (model_mc.cbm, multiclass) для plugin pipeline.

    model_dir: папка с model_mc.cbm + class_mapping.json (stage2_multiclass/models/catboost)
    threshold: порог срабатывания (default 0.70)
    """

    def __init__(self, model_dir: str | Path, threshold: float = 0.70) -> None:
        self._model_dir = Path(model_dir)
        self._threshold = threshold
        self._adapter   = None

    # ── BaseModel interface ────────────────────────────────────────────────────

    def get_name(self) -> str:
        return "builtin_stage2_multiclass"

    def get_description(self) -> str:
        return (
            "Stage2: многоклассовый CatBoost (71 CICFlowMeter признаков, 8 классов). "
            "Используется после Stage1 gate в Simple режиме."
        )

    def get_version(self) -> str:
        return "1.0.0"

    def get_accepted_schema_ids(self) -> list[str]:
        return ["cicflowmeter_71"]

    def get_output_classes(self) -> list[str]:
        if self._adapter and self._adapter._class_mapping:
            return list(self._adapter._class_mapping.values())
        return ["Benign", "DoS", "DDoS", "Recon", "BruteForce", "WebAttack", "Bot", "Spoofing"]

    def on_load(self) -> None:
        from app.model.catboost_adapter import CatBoostModelAdapter
        self._adapter = CatBoostModelAdapter(
            model_dir=self._model_dir,
            model_id="builtin_stage2_multiclass",
            threshold=self._threshold,
        )

    def on_unload(self) -> None:
        self._adapter = None

    def predict(self, features: PluginFeatureVector) -> PluginVerdict:
        if self._adapter is None:
            raise RuntimeError(
                "BuiltinStage2Model не загружен. "
                "Вызови on_load() или зарегистрируй в PluginRegistry."
            )

        ok, reason = self.check_compatibility(features.schema_id)
        if not ok:
            raise ValueError(reason)

        fv = _to_feature_vector(features)
        result = self._adapter.infer(fv)
        return _to_plugin_verdict(result, stage="stage2")
