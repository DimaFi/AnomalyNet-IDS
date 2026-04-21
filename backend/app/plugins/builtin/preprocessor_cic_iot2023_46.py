"""
Builtin wrapper: CIC2023StandalonePipeline → BasePreprocessor.

Обёртывает CIC2023StandalonePipeline (46 признаков CIC IoT 2023).
Принимает NormalizedFlowEvent (с заполненным raw_features_cic2023),
возвращает PluginFeatureVector со schema_id="cic_iot2023_46".

Требует detection_mode="advanced" в настройках, чтобы scapy-адаптер
вычислял raw_features_cic2023.
"""
from __future__ import annotations

from pathlib import Path

from app.plugins.base_preprocessor import BasePreprocessor
from app.plugins.contracts import RAW_FLOW, PluginFeatureVector


class BuiltinCicIot2023_46Preprocessor(BasePreprocessor):
    """
    Wraps CIC2023StandalonePipeline для использования в plugin pipeline.

    artifacts_dir: путь к папке с feature_contract.json и preprocessing_params.json
    (артефакты stage3_cic2023)
    """

    def __init__(self, artifacts_dir: str | Path) -> None:
        self._artifacts_dir = Path(artifacts_dir)
        self._pipeline = None

    # ── BasePreprocessor interface ─────────────────────────────────────────────

    def get_name(self) -> str:
        return "cic_iot2023_46"

    def get_description(self) -> str:
        return "46 CIC IoT 2023 признаков (Stage3): предобработка из артефактов stage3_cic2023"

    def get_version(self) -> str:
        return "1.0.0"

    def get_input_type(self) -> str:
        return RAW_FLOW

    def get_output_schema_id(self) -> str:
        return "cic_iot2023_46"

    def get_feature_names(self) -> list[str]:
        if self._pipeline is None:
            return []
        return list(self._pipeline._feature_names)

    def on_load(self) -> None:
        from app.preprocess.cic2023_pipeline import CIC2023StandalonePipeline
        self._pipeline = CIC2023StandalonePipeline(self._artifacts_dir)

    def on_unload(self) -> None:
        self._pipeline = None

    def transform(self, raw_input) -> PluginFeatureVector:
        """
        raw_input: NormalizedFlowEvent с заполненным raw_features_cic2023.
        Delegates to CIC2023StandalonePipeline.transform().
        """
        if self._pipeline is None:
            raise RuntimeError(
                "BuiltinCicIot2023_46Preprocessor не загружен. "
                "Вызови on_load() или зарегистрируй в PluginRegistry."
            )

        fv = self._pipeline.transform(raw_input)

        feature_names = list(fv.values.keys())
        features = [float(fv.values[n]) for n in feature_names]

        return PluginFeatureVector(
            features=features,
            feature_names=feature_names,
            schema_id="cic_iot2023_46",
            meta={
                "event_id": fv.event_id,
                "src_ip":   fv.src_ip or "",
            },
        )
