"""
CatBoost model adapter.

Loads model.cbm once at init. Aligns features by name (using model.feature_names_),
applies predict_proba, then maps probability to verdict using configurable threshold.
"""

from __future__ import annotations

from pathlib import Path

from app.contracts.schemas import FeatureVector, InferenceResult


class CatBoostModelAdapter:
    def __init__(
        self,
        model_dir: Path | str,
        model_id: str,
        threshold: float = 0.70,
    ) -> None:
        from catboost import CatBoostClassifier
        import numpy as np

        self._model_id = model_id
        self._threshold = threshold
        self._np = np

        model_path = Path(model_dir) / "model.cbm"
        if not model_path.exists():
            raise FileNotFoundError(f"CatBoost model not found: {model_path}")

        self._model = CatBoostClassifier()
        self._model.load_model(str(model_path))

        # Feature names in training order — use for alignment
        self._feature_names: list[str] = list(self._model.feature_names_)

    def infer(self, features: FeatureVector) -> InferenceResult:
        row = self._np.array(
            [float(features.values.get(name, 0.0)) for name in self._feature_names],
            dtype=self._np.float64,
        ).reshape(1, -1)

        proba = float(self._model.predict_proba(row)[0][1])  # class 1 = attack

        if proba >= 0.85:
            label = "anomaly"
            reason = (
                f"Высокая вероятность атаки: {proba:.3f} "
                f"(порог {self._threshold}, уровень опасности: критический)"
            )
        elif proba >= self._threshold:
            label = "warning"
            reason = (
                f"Подозрительный трафик: вероятность атаки {proba:.3f} "
                f"≥ порог {self._threshold}"
            )
        else:
            label = "normal"
            reason = (
                f"Нормальный трафик: вероятность атаки {proba:.3f} "
                f"< порог {self._threshold}"
            )

        return InferenceResult(
            event_id=features.event_id,
            label=label,
            score=round(proba, 4),
            reason=reason,
            model_id=self._model_id,
        )
