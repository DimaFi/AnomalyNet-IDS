"""
Пример пользовательской модели для AnomalyNet.

Скопируй этот файл, реализуй predict() и положи в папку plugins/.
Модель загрузится при следующем старте или через POST /api/plugins/reload.

ВАЖНО: get_accepted_schema_ids() должен совпадать с get_output_schema_id() препроцессора.
"""
from __future__ import annotations

from app.plugins.base_model import BaseModel
from app.plugins.contracts import PluginFeatureVector, PluginVerdict


class MyCustomModel(BaseModel):
    """
    Шаблон пользовательской модели.

    Замени логику predict() на свою модель.
    Если нужно загружать файл модели — делай это в on_load().
    """

    def get_name(self) -> str:
        return "my_custom_model"   # уникальный ключ

    def get_description(self) -> str:
        return "Моя пользовательская модель"

    def get_version(self) -> str:
        return "1.0.0"

    def get_accepted_schema_ids(self) -> list[str]:
        return ["my_schema_v1"]   # должен совпадать с get_output_schema_id() препроцессора

    def get_output_classes(self) -> list[str]:
        return ["Benign", "Attack"]

    def on_load(self) -> None:
        """Загрузка модели при регистрации."""
        # Пример:
        # import joblib
        # self._model = joblib.load("/path/to/model.pkl")
        pass

    def predict(self, features: PluginFeatureVector) -> PluginVerdict:
        """
        features.features      — list[float] признаков
        features.feature_names — list[str] имён признаков
        features.schema_id     — должен быть в get_accepted_schema_ids()
        features.meta          — dict с event_id, src_ip и т.д.
        """
        # Проверка совместимости схемы (рекомендуется)
        ok, reason = self.check_compatibility(features.schema_id)
        if not ok:
            raise ValueError(reason)

        # Пример простой эвристики (замени на реальную модель)
        feat_dict = dict(zip(features.feature_names, features.features))
        bytes_per_packet = feat_dict.get("feature_a", 0.0)

        if bytes_per_packet > 10000:
            score, verdict, attack_class = 0.92, "anomaly", "DDoS"
        elif bytes_per_packet > 5000:
            score, verdict, attack_class = 0.75, "warning", "DoS"
        else:
            score, verdict, attack_class = 0.10, "normal", None

        return PluginVerdict(
            score=score,
            verdict=verdict,
            attack_class=attack_class,
            model_name=self.get_name(),
            stage="custom",
            reason=f"bytes_per_packet={bytes_per_packet:.1f}",
        )
