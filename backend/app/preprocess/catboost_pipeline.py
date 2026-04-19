"""
CatBoost preprocessing pipeline.

Loads feature_contract.json and preprocessing_params.json once on init,
then applies the identical inf→NaN→fill transform that was used during training.
StandardScaler is NOT applied — CatBoost does not need feature scaling.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from app.contracts.schemas import FeatureVector, NormalizedFlowEvent
from app.preprocess.contracts import CATBOOST_CONTRACT_VERSION, CATBOOST_PROFILE_NAME


class CatBoostPreprocessingPipeline:
    def __init__(self, artifacts_dir: Path) -> None:
        artifacts_dir = Path(artifacts_dir)
        contract_path = artifacts_dir / "feature_contract.json"
        params_path   = artifacts_dir / "preprocessing_params.json"

        if not contract_path.exists():
            raise FileNotFoundError(f"Feature contract not found: {contract_path}")
        if not params_path.exists():
            raise FileNotFoundError(f"Preprocessing params not found: {params_path}")

        self._feature_names: list[str] = json.loads(
            contract_path.read_text(encoding="utf-8")
        )
        params = json.loads(params_path.read_text(encoding="utf-8"))
        self._fill_values: dict[str, float] = params["fill_values"]

    def transform(self, event: NormalizedFlowEvent) -> FeatureVector:
        if event.raw_features is None:
            raise ValueError(
                f"CatBoostPreprocessingPipeline requires raw_features on "
                f"NormalizedFlowEvent (event_id={event.event_id}). "
                f"Use run_mode=linux_live."
            )

        raw = event.raw_features
        values: dict[str, float] = {}

        for name in self._feature_names:
            v = raw.get(name)
            if v is None:
                v = self._fill_values.get(name, 0.0)
            elif not isinstance(v, (int, float)) or math.isinf(v) or math.isnan(v):
                v = self._fill_values.get(name, 0.0)
            values[name] = float(v)

        return FeatureVector(
            event_id=event.event_id,
            contract_version=CATBOOST_CONTRACT_VERSION,
            profile_name=CATBOOST_PROFILE_NAME,
            values=values,
            src_ip=event.src_ip,
        )
