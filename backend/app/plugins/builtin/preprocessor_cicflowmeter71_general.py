"""
Builtin wrapper: CatBoostPreprocessingPipeline → BasePreprocessor (General Network).

Идентичен cicflowmeter71, но загружает артефакты из catboost_general_artifacts_dir
(медианы, вычисленные по CICIDS 2017, а не IoT-DIAD 2024).
schema_id = "cicflowmeter_71_general" — отдельный ID чтобы не конфликтовать с IoT-моделями.
"""
from __future__ import annotations

from pathlib import Path

from app.plugins.base_preprocessor import BasePreprocessor
from app.plugins.contracts import RAW_FLOW, PluginFeatureVector


class BuiltinCicFlowMeter71GeneralPreprocessor(BasePreprocessor):
    """
    Wraps CatBoostPreprocessingPipeline для General Network pipeline.
    Артефакты содержат медианы CICIDS 2017 вместо IoT-DIAD 2024.
    """

    def __init__(self, artifacts_dir: str | Path) -> None:
        self._artifacts_dir = Path(artifacts_dir)
        self._pipeline = None

    def get_name(self) -> str:
        return "cicflowmeter_71_general"

    def get_description(self) -> str:
        return "71 CICFlowMeter признак (General Network): медианы CICIDS 2017, ПК/домашние сети"

    def get_version(self) -> str:
        return "1.0.0"

    def get_input_type(self) -> str:
        return RAW_FLOW

    def get_output_schema_id(self) -> str:
        return "cicflowmeter_71_general"

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
        if self._pipeline is None:
            raise RuntimeError("BuiltinCicFlowMeter71GeneralPreprocessor не загружен.")

        fv = self._pipeline.transform(raw_input)

        feature_names = list(fv.values.keys())
        features = [float(fv.values[n]) for n in feature_names]

        return PluginFeatureVector(
            features=features,
            feature_names=feature_names,
            schema_id="cicflowmeter_71_general",
            meta={
                "event_id": fv.event_id,
                "src_ip":   fv.src_ip or "",
            },
        )
