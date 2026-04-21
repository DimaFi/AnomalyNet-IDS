"""
Builtin wrapper: CascadeAdvancedPipeline → BasePreprocessor.

Обёртывает CascadeAdvancedPipeline (71 + 46 признаков, dual-mode).
schema_id = "cascade_dual" — специальный тип: features содержит 71 признак
(Stage1/Stage2), meta["secondary_features"] — 46 признаков CIC2023 (Stage3).

Используется только с CascadeAdvancedAdapter или CascadeRoutedAdapter через
plugin pipeline. Требует detection_mode="advanced" для вычисления secondary.
"""
from __future__ import annotations

from pathlib import Path

from app.plugins.base_preprocessor import BasePreprocessor
from app.plugins.contracts import RAW_FLOW, PluginFeatureVector


class BuiltinCascadeDualPreprocessor(BasePreprocessor):
    """
    Wraps CascadeAdvancedPipeline для plugin pipeline.

    primary_artifacts_dir:   артефакты Stage1/Stage2 (71 признак)
    secondary_artifacts_dir: артефакты Stage3 CIC2023 (46 признаков)
    """

    def __init__(
        self,
        primary_artifacts_dir: str | Path,
        secondary_artifacts_dir: str | Path,
    ) -> None:
        self._primary_dir   = Path(primary_artifacts_dir)
        self._secondary_dir = Path(secondary_artifacts_dir)
        self._pipeline      = None

    # ── BasePreprocessor interface ─────────────────────────────────────────────

    def get_name(self) -> str:
        return "cascade_dual"

    def get_description(self) -> str:
        return (
            "Dual cascade: 71 CICFlowMeter (Stage1/Stage2) + "
            "46 CIC IoT 2023 (Stage3) признаков"
        )

    def get_version(self) -> str:
        return "1.0.0"

    def get_input_type(self) -> str:
        return RAW_FLOW

    def get_output_schema_id(self) -> str:
        return "cascade_dual"

    def get_feature_names(self) -> list[str]:
        """Возвращает имена первичных признаков (71 CICFlowMeter)."""
        if self._pipeline is None:
            return []
        return list(self._pipeline._primary._feature_names)

    def on_load(self) -> None:
        from app.preprocess.cascade_pipeline import CascadeAdvancedPipeline
        self._pipeline = CascadeAdvancedPipeline(
            primary_artifacts_dir=self._primary_dir,
            secondary_artifacts_dir=self._secondary_dir,
        )

    def on_unload(self) -> None:
        self._pipeline = None

    def transform(self, raw_input) -> PluginFeatureVector:
        """
        raw_input: NormalizedFlowEvent.
        Возвращает PluginFeatureVector:
          features      = 71 CICFlowMeter (primary)
          meta["secondary_features"]      = 46 CIC2023 или [] если недоступны
          meta["secondary_feature_names"] = имена secondary признаков
        """
        if self._pipeline is None:
            raise RuntimeError(
                "BuiltinCascadeDualPreprocessor не загружен. "
                "Вызови on_load() или зарегистрируй в PluginRegistry."
            )

        fv = self._pipeline.transform(raw_input)   # FeatureVector с values + secondary_values

        feature_names = list(fv.values.keys())
        features = [float(fv.values[n]) for n in feature_names]

        # Secondary features (46 CIC2023) — могут быть None если поток слишком короткий
        if fv.secondary_values is not None:
            sec_names    = list(fv.secondary_values.keys())
            sec_features = [float(fv.secondary_values[n]) for n in sec_names]
        else:
            sec_names    = []
            sec_features = []

        return PluginFeatureVector(
            features=features,
            feature_names=feature_names,
            schema_id="cascade_dual",
            meta={
                "event_id":                fv.event_id,
                "src_ip":                  fv.src_ip or "",
                "secondary_features":      sec_features,
                "secondary_feature_names": sec_names,
            },
        )
