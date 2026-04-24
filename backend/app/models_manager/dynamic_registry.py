"""
Dynamic model registration from scanned ModelPackage objects.

For each valid ModelPackage:
  - Registers a DynamicPreprocessor (wraps existing pipeline classes)
  - Registers a DynamicCatBoostModel
  - Auto-creates a PipelineConfig (single-stage or cascade via cascade_next)

Naming convention (avoids conflicts with builtin plugin names):
  preprocessor name : "preproc_dyn_{package.id}"
  model name        : "model_dyn_{package.id}"
  schema id         : "schema_dyn_{package.id}"
  pipeline name     : "dyn_{package.id}"          (single-stage)
  pipeline name     : "dyn_{gate.id}__cascade"    (cascade)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.plugins.base_model import BaseModel
from app.plugins.base_preprocessor import BasePreprocessor
from app.plugins.contracts import RAW_FLOW, PluginFeatureVector, PluginVerdict
from app.plugins.pipeline_config import PipelineConfig, StageConfig

if TYPE_CHECKING:
    from app.models_manager.package import ModelPackage
    from app.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


# ── Dynamic preprocessor ──────────────────────────────────────────────────────

class DynamicPreprocessor(BasePreprocessor):
    """
    Preprocessor dynamically created from a ModelPackage.
    Supports cicflowmeter_71 and ciciot_2023_46 pipeline types.
    """

    def __init__(self, package: "ModelPackage") -> None:
        self._pkg = package
        self._pipeline = None
        self._schema_id = f"schema_dyn_{package.id}"

    def get_name(self) -> str:
        return f"preproc_dyn_{self._pkg.id}"

    def get_description(self) -> str:
        return f"[dynamic] {self._pkg.name} preprocessor ({self._pkg.preprocessor})"

    def get_version(self) -> str:
        return self._pkg.version

    def get_input_type(self) -> str:
        return RAW_FLOW

    def get_output_schema_id(self) -> str:
        return self._schema_id

    def get_feature_names(self) -> list[str]:
        if self._pipeline is None:
            return []
        return list(getattr(self._pipeline, "_feature_names", []))

    def on_load(self) -> None:
        arts = self._pkg.artifacts_dir
        if self._pkg.preprocessor == "ciciot_2023_46":
            from app.preprocess.cic2023_pipeline import CIC2023StandalonePipeline
            self._pipeline = CIC2023StandalonePipeline(arts)
        else:
            # Default: cicflowmeter_71 (and any future 71-feature variants)
            from app.preprocess.catboost_pipeline import CatBoostPreprocessingPipeline
            self._pipeline = CatBoostPreprocessingPipeline(arts)

    def on_unload(self) -> None:
        self._pipeline = None

    def transform(self, raw_input) -> PluginFeatureVector:
        if self._pipeline is None:
            raise RuntimeError(f"DynamicPreprocessor for {self._pkg.id!r} not loaded")

        fv = self._pipeline.transform(raw_input)

        feature_names = list(fv.values.keys())
        features = [float(fv.values[n]) for n in feature_names]
        return PluginFeatureVector(
            features=features,
            feature_names=feature_names,
            schema_id=self._schema_id,
            meta={
                "event_id": fv.event_id,
                "src_ip": fv.src_ip or "",
            },
        )


# ── Dynamic model ─────────────────────────────────────────────────────────────

class DynamicCatBoostModel(BaseModel):
    """
    BaseModel wrapping a CatBoost model loaded directly from a .cbm file.
    class_mapping.json (for multiclass) is loaded from artifacts_dir.
    """

    def __init__(self, package: "ModelPackage", threshold: float | None = None) -> None:
        self._pkg = package
        self._threshold = threshold if threshold is not None else package.threshold
        self._model = None
        self._feature_names: list[str] = []
        self._class_mapping: dict[int, str] = {}
        self._multiclass = (package.model_type == "multiclass")
        self._schema_id = f"schema_dyn_{package.id}"

    def get_name(self) -> str:
        return f"model_dyn_{self._pkg.id}"

    def get_description(self) -> str:
        return f"[dynamic] {self._pkg.name} ({self._pkg.model_type})"

    def get_version(self) -> str:
        return self._pkg.version

    def get_accepted_schema_ids(self) -> list[str]:
        return [self._schema_id]

    def get_output_classes(self) -> list[str]:
        if self._class_mapping:
            return list(self._class_mapping.values())
        return ["Benign", "Attack"]

    def on_load(self) -> None:
        import numpy as np
        from catboost import CatBoostClassifier

        self._np = np
        model_path = self._pkg.model_file
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        self._model = CatBoostClassifier()
        self._model.load_model(str(model_path))
        self._feature_names = list(self._model.feature_names_)

        mapping_path = self._pkg.artifacts_dir / "class_mapping.json"
        if mapping_path.exists():
            raw = json.loads(mapping_path.read_text(encoding="utf-8"))
            self._class_mapping = {int(k): v for k, v in raw.items()}
            self._multiclass = True
        else:
            self._multiclass = False

    def on_unload(self) -> None:
        self._model = None
        self._feature_names = []

    def predict(self, features: PluginFeatureVector) -> PluginVerdict:
        if self._model is None:
            raise RuntimeError(f"DynamicCatBoostModel for {self._pkg.id!r} not loaded")

        ok, reason = self.check_compatibility(features.schema_id)
        if not ok:
            raise ValueError(reason)

        row = self._np.array(
            [float(dict(zip(features.feature_names, features.features)).get(name, 0.0))
             for name in self._feature_names],
            dtype=self._np.float64,
        ).reshape(1, -1)

        proba_matrix = self._model.predict_proba(row)

        event_id = features.meta.get("event_id", "")
        if self._multiclass:
            return self._predict_multiclass(event_id, proba_matrix[0])
        else:
            return self._predict_binary(event_id, float(proba_matrix[0][1]))

    def _predict_binary(self, event_id: str, proba: float) -> PluginVerdict:
        t = self._threshold
        if proba >= 0.85:
            verdict, reason = "anomaly", f"Высокая вероятность атаки: {proba:.3f}"
        elif proba >= t:
            verdict, reason = "warning", f"Подозрительный трафик: {proba:.3f} ≥ {t}"
        else:
            verdict, reason = "normal", f"Нормальный трафик: {proba:.3f} < {t}"
        return PluginVerdict(
            score=round(proba, 4),
            verdict=verdict,
            attack_class=None,
            model_name=self.get_name(),
            stage="stage1",
            reason=reason,
        )

    def _predict_multiclass(self, event_id: str, proba_vec) -> PluginVerdict:
        class_id = int(self._np.argmax(proba_vec))
        max_proba = float(proba_vec[class_id])
        class_name = self._class_mapping.get(class_id, f"Class{class_id}")
        t = self._threshold

        if class_id == 0:
            verdict, attack_class = "normal", None
            reason = f"Нормальный трафик (уверенность {max_proba:.3f})"
        elif max_proba >= 0.85:
            verdict, attack_class = "anomaly", class_name
            reason = f"Обнаружена атака: {class_name} (уверенность {max_proba:.3f})"
        elif max_proba >= t:
            verdict, attack_class = "warning", class_name
            reason = f"Подозрительный трафик: {class_name} ({max_proba:.3f})"
        else:
            verdict, attack_class = "normal", None
            reason = f"Низкая уверенность: возможно {class_name} ({max_proba:.3f} < {t})"

        return PluginVerdict(
            score=round(max_proba, 4),
            verdict=verdict,
            attack_class=attack_class,
            model_name=self.get_name(),
            stage="stage2",
            reason=reason,
        )


# ── Registration ──────────────────────────────────────────────────────────────

def register_packages(
    packages: list["ModelPackage"],
    registry: "PluginRegistry",
    default_threshold: float = 0.70,
) -> None:
    """
    Register all valid ModelPackages in the given PluginRegistry.

    For each package: registers a DynamicPreprocessor + DynamicCatBoostModel.
    For gate packages with a valid cascade_next: auto-creates a cascade PipelineConfig.
    For every package: creates a single-stage PipelineConfig.
    """
    pkg_map = {p.id: p for p in packages}

    for pkg in packages:
        try:
            registry.register_preprocessor(DynamicPreprocessor(pkg))
            registry.register_model(DynamicCatBoostModel(pkg, default_threshold))
            logger.info("Registered dynamic package: %s (%s)", pkg.id, pkg.model_type)
        except Exception as exc:
            logger.warning("Failed to register package %r: %s", pkg.id, exc)
            continue

    # Build pipeline configs
    registered_cascade: set[str] = set()

    for pkg in packages:
        # Single-stage pipeline (always created)
        try:
            single = PipelineConfig(
                name=f"dyn_{pkg.id}",
                description=pkg.description or pkg.name,
                entry_stage="stage1",
                stages={
                    "stage1": StageConfig(
                        preprocessor_name=f"preproc_dyn_{pkg.id}",
                        model_name=f"model_dyn_{pkg.id}",
                        threshold=pkg.threshold,
                        is_gate=False,
                        next_stage=None,
                    ),
                },
                is_builtin=False,
            )
            registry.register_pipeline(single)
        except Exception as exc:
            logger.warning("Failed to create single-stage pipeline for %r: %s", pkg.id, exc)

        # Cascade pipeline (if this package is a gate and cascade_next exists)
        if pkg.is_gate and pkg.cascade_next and pkg.cascade_next in pkg_map:
            cascade_key = f"{pkg.id}→{pkg.cascade_next}"
            if cascade_key in registered_cascade:
                continue
            next_pkg = pkg_map[pkg.cascade_next]
            try:
                cascade = PipelineConfig(
                    name=f"dyn_{pkg.id}__cascade",
                    description=(
                        f"{pkg.name} → {next_pkg.name}"
                    ),
                    entry_stage="stage1",
                    stages={
                        "stage1": StageConfig(
                            preprocessor_name=f"preproc_dyn_{pkg.id}",
                            model_name=f"model_dyn_{pkg.id}",
                            threshold=pkg.threshold,
                            is_gate=True,
                            next_stage="stage2",
                        ),
                        "stage2": StageConfig(
                            preprocessor_name=f"preproc_dyn_{next_pkg.id}",
                            model_name=f"model_dyn_{next_pkg.id}",
                            threshold=next_pkg.threshold,
                            is_gate=False,
                            next_stage=None,
                        ),
                    },
                    is_builtin=False,
                )
                registry.register_pipeline(cascade)
                registered_cascade.add(cascade_key)
                logger.info("Created cascade pipeline: %s", cascade.name)
            except Exception as exc:
                logger.warning(
                    "Failed to create cascade pipeline %s: %s", cascade_key, exc
                )
