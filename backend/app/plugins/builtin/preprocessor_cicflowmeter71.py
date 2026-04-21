"""
Builtin wrapper: CatBoostPreprocessingPipeline → BasePreprocessor.

Обёртывает существующий CatBoostPreprocessingPipeline (71 признак CICFlowMeter)
не изменяя его логики. Принимает NormalizedFlowEvent, возвращает PluginFeatureVector
со schema_id="cicflowmeter_71".
"""
from __future__ import annotations

from pathlib import Path

from app.plugins.base_preprocessor import BasePreprocessor
from app.plugins.contracts import RAW_FLOW, PluginFeatureVector


class BuiltinCicFlowMeter71Preprocessor(BasePreprocessor):
    """
    Wraps CatBoostPreprocessingPipeline для использования в plugin pipeline.

    artifacts_dir: путь к папке с feature_contract.json и preprocessing_params.json
    (те же артефакты что использует catboost_pipeline.py напрямую)
    """

    def __init__(self, artifacts_dir: str | Path) -> None:
        self._artifacts_dir = Path(artifacts_dir)
        self._pipeline = None  # ленивая инициализация в on_load()

    # ── BasePreprocessor interface ─────────────────────────────────────────────

    def get_name(self) -> str:
        return "cicflowmeter_71"

    def get_description(self) -> str:
        return "71 CICFlowMeter признак (Stage1/Stage2): предобработка из артефактов stage1_v2_cl"

    def get_version(self) -> str:
        return "1.0.0"

    def get_input_type(self) -> str:
        return RAW_FLOW

    def get_output_schema_id(self) -> str:
        return "cicflowmeter_71"

    def get_feature_names(self) -> list[str]:
        if self._pipeline is None:
            return []
        return list(self._pipeline._feature_names)

    def on_load(self) -> None:
        from app.preprocess.catboost_pipeline import CatBoostPreprocessingPipeline
        self._pipeline = CatBoostPreprocessingPipeline(self._artifacts_dir)

    def on_unload(self) -> None:
        self._pipeline = None

    def transform(self, raw_input) -> PluginFeatureVector:
        """
        raw_input: NormalizedFlowEvent (из существующего pipeline)
        Delegates to CatBoostPreprocessingPipeline.transform(), конвертирует
        dict-based FeatureVector → PluginFeatureVector(list[float]).
        """
        if self._pipeline is None:
            raise RuntimeError(
                "BuiltinCicFlowMeter71Preprocessor не загружен. "
                "Вызови on_load() или зарегистрируй в PluginRegistry."
            )

        fv = self._pipeline.transform(raw_input)   # → FeatureVector(values: dict)

        feature_names = list(fv.values.keys())
        features = [float(fv.values[n]) for n in feature_names]

        return PluginFeatureVector(
            features=features,
            feature_names=feature_names,
            schema_id="cicflowmeter_71",
            meta={
                "event_id": fv.event_id,
                "src_ip":   fv.src_ip or "",
            },
        )
