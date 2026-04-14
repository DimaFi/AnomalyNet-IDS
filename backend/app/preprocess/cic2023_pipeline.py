"""
Standalone CIC IoT 2023 preprocessing pipeline (Stage4 / Stage3 standalone).

Reads from event.raw_features_cic2023 (46 features computed by
feature_computer_cic2023.py) and returns them as values in FeatureVector.

Used for standalone multiclass models that classify traffic directly
using 46 CIC IoT 2023 features without a binary pre-filter (Stage1).
Requires detection_mode == "advanced" in settings so that the scapy
adapter computes raw_features_cic2023.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from app.contracts.schemas import FeatureVector, NormalizedFlowEvent
from app.preprocess.contracts import CATBOOST_CONTRACT_VERSION, CATBOOST_CIC2023_PROFILE


class CIC2023StandalonePipeline:
    """
    Preprocessing pipeline for standalone 46-feature CIC IoT 2023 models.

    Loads feature_contract.json and preprocessing_params.json from
    artifacts_dir, applies inf/NaN fill, returns FeatureVector with
    profile_name = 'catboost_iot_46_cic2023'.
    """

    def __init__(self, artifacts_dir: Path | str) -> None:
        artifacts_dir = Path(artifacts_dir)
        contract_path = artifacts_dir / "feature_contract.json"
        params_path   = artifacts_dir / "preprocessing_params.json"

        if not contract_path.exists():
            raise FileNotFoundError(f"CIC2023 feature contract not found: {contract_path}")
        if not params_path.exists():
            raise FileNotFoundError(f"CIC2023 preprocessing params not found: {params_path}")

        self._feature_names: list[str] = json.loads(
            contract_path.read_text(encoding="utf-8")
        )
        params = json.loads(params_path.read_text(encoding="utf-8"))
        self._fill_values: dict[str, float] = params["fill_values"]

    def transform(self, event: NormalizedFlowEvent) -> FeatureVector:
        if event.raw_features_cic2023 is None:
            raise ValueError(
                f"CIC2023StandalonePipeline requires raw_features_cic2023 on "
                f"NormalizedFlowEvent (event_id={event.event_id}). "
                f"Set detection_mode='advanced' in settings."
            )

        raw = event.raw_features_cic2023
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
            profile_name=CATBOOST_CIC2023_PROFILE,
            values=values,
        )
