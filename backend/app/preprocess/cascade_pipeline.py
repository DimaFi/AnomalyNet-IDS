"""
Cascade preprocessing pipeline for Advanced detection mode.

Produces a FeatureVector with:
  values          — 71 CICFlowMeter features (for Stage1 binary gate)
  secondary_values — 46 CIC IoT 2023 features (for Stage3 multiclass classifier)

Used only when detection_mode == "advanced".
For "simple" mode, the standard CatBoostPreprocessingPipeline handles everything.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from app.contracts.schemas import FeatureVector, NormalizedFlowEvent
from app.preprocess.catboost_pipeline import CatBoostPreprocessingPipeline
from app.preprocess.contracts import (
    CATBOOST_CONTRACT_VERSION,
    CATBOOST_CASCADE_ADV_PROFILE,
)


class CascadeAdvancedPipeline:
    """
    Wraps two CatBoostPreprocessingPipeline instances:
      - primary: 71 CICFlowMeter features (artifacts from stage1/stage2)
      - secondary: 46 CIC IoT 2023 features (artifacts from stage3_cic2023)
    """

    def __init__(
        self,
        primary_artifacts_dir: Path | str,
        secondary_artifacts_dir: Path | str,
    ) -> None:
        self._primary = CatBoostPreprocessingPipeline(
            artifacts_dir=Path(primary_artifacts_dir)
        )

        secondary_artifacts_dir = Path(secondary_artifacts_dir)
        contract_path = secondary_artifacts_dir / "feature_contract.json"
        params_path   = secondary_artifacts_dir / "preprocessing_params.json"

        if not contract_path.exists():
            raise FileNotFoundError(
                f"CIC2023 feature contract not found: {contract_path}"
            )
        if not params_path.exists():
            raise FileNotFoundError(
                f"CIC2023 preprocessing params not found: {params_path}"
            )

        self._sec_features: list[str] = json.loads(
            contract_path.read_text(encoding="utf-8")
        )
        params = json.loads(params_path.read_text(encoding="utf-8"))
        self._sec_fill: dict[str, float] = params["fill_values"]

    def transform(self, event: NormalizedFlowEvent) -> FeatureVector:
        # Primary transform: 71 CICFlowMeter features → values
        fv = self._primary.transform(event)

        # Secondary transform: 46 CIC2023 features → secondary_values
        secondary_values: dict[str, float] | None = None

        if event.raw_features_cic2023 is not None:
            raw = event.raw_features_cic2023
            sec: dict[str, float] = {}
            for name in self._sec_features:
                v = raw.get(name)
                if v is None:
                    v = self._sec_fill.get(name, 0.0)
                elif not isinstance(v, (int, float)) or math.isinf(v) or math.isnan(v):
                    v = self._sec_fill.get(name, 0.0)
                sec[name] = float(v)
            secondary_values = sec

        return FeatureVector(
            event_id=fv.event_id,
            contract_version=CATBOOST_CONTRACT_VERSION,
            profile_name=CATBOOST_CASCADE_ADV_PROFILE,
            values=fv.values,
            secondary_values=secondary_values,
        )
