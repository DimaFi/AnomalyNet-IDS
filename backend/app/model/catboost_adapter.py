"""
CatBoost model adapter — поддерживает бинарную и многоклассовую модели.

Автодетект: если в model_dir лежит class_mapping.json — многоклассовый режим.
Иначе — бинарный (обратная совместимость с stage1).
"""
from __future__ import annotations

import json
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

        self._model_id  = model_id
        self._threshold = threshold
        self._np        = np

        model_dir = Path(model_dir)

        # Пробуем multiclass-модель, потом binary
        mc_path  = model_dir / "model_mc.cbm"
        bin_path = model_dir / "model.cbm"

        if mc_path.exists():
            model_path = mc_path
        elif bin_path.exists():
            model_path = bin_path
        else:
            raise FileNotFoundError(
                f"Не найден ни model_mc.cbm, ни model.cbm в {model_dir}"
            )

        self._model = CatBoostClassifier()
        self._model.load_model(str(model_path))
        self._feature_names: list[str] = list(self._model.feature_names_)

        # Загружаем маппинг классов (если есть — многоклассовый режим)
        mapping_path = model_dir / "class_mapping.json"
        if mapping_path.exists():
            with open(mapping_path, encoding="utf-8") as f:
                raw = json.load(f)
            # ключи — строки "0","1",...
            self._class_mapping: dict[int, str] = {int(k): v for k, v in raw.items()}
            self._multiclass = True
            print(f"[CatBoost] Многоклассовый режим: {self._class_mapping}")
        else:
            self._class_mapping = {}
            self._multiclass    = False
            print("[CatBoost] Бинарный режим")

    def infer(self, features: FeatureVector) -> InferenceResult:
        row = self._np.array(
            [float(features.values.get(name, 0.0)) for name in self._feature_names],
            dtype=self._np.float64,
        ).reshape(1, -1)

        proba_matrix = self._model.predict_proba(row)  # (1, N_classes)

        if self._multiclass:
            return self._infer_multiclass(features.event_id, proba_matrix[0])
        else:
            return self._infer_binary(features.event_id, float(proba_matrix[0][1]))

    # ── Бинарный режим ─────────────────────────────────────────
    def _infer_binary(self, event_id: str, proba: float) -> InferenceResult:
        if proba >= 0.85:
            label  = "anomaly"
            reason = (
                f"Высокая вероятность атаки: {proba:.3f} "
                f"(уровень: критический)"
            )
        elif proba >= self._threshold:
            label  = "warning"
            reason = (
                f"Подозрительный трафик: вероятность {proba:.3f} "
                f"≥ порог {self._threshold}"
            )
        else:
            label  = "normal"
            reason = (
                f"Нормальный трафик: вероятность {proba:.3f} "
                f"< порог {self._threshold}"
            )
        return InferenceResult(
            event_id=event_id,
            label=label,
            score=round(proba, 4),
            reason=reason,
            model_id=self._model_id,
            attack_class=None,
        )

    # ── Многоклассовый режим ───────────────────────────────────
    def _infer_multiclass(self, event_id: str, proba_vec) -> InferenceResult:
        class_id  = int(self._np.argmax(proba_vec))
        max_proba = float(proba_vec[class_id])
        class_name = self._class_mapping.get(class_id, f"Class{class_id}")

        if class_id == 0:
            # Benign
            label        = "normal"
            attack_class = None
            reason       = f"Нормальный трафик (уверенность {max_proba:.3f})"
        else:
            attack_class = class_name
            if max_proba >= 0.85:
                label  = "anomaly"
                reason = (
                    f"Обнаружена атака: {class_name} "
                    f"(уверенность {max_proba:.3f}, уровень: критический)"
                )
            elif max_proba >= self._threshold:
                label  = "warning"
                reason = (
                    f"Подозрительный трафик: вероятный {class_name} "
                    f"(уверенность {max_proba:.3f})"
                )
            else:
                # Низкая уверенность — всё равно помечаем, но как warning
                label  = "warning"
                reason = (
                    f"Неоднозначный трафик: возможно {class_name} "
                    f"(уверенность {max_proba:.3f} < порог {self._threshold})"
                )

        return InferenceResult(
            event_id=event_id,
            label=label,
            score=round(max_proba, 4),
            reason=reason,
            model_id=self._model_id,
            attack_class=attack_class,
        )
