"""
Пример пользовательского препроцессора для AnomalyNet.

Скопируй этот файл, переименуй, реализуй все методы и положи в папку plugins/.
Плагин загрузится автоматически при следующем старте или через API POST /api/plugins/reload.

ВАЖНО: имя класса должно быть уникальным; get_name() возвращает ключ регистрации.
"""
from __future__ import annotations

from app.plugins.base_preprocessor import BasePreprocessor
from app.plugins.contracts import RAW_FLOW, PluginFeatureVector


class MyCustomPreprocessor(BasePreprocessor):
    """
    Шаблон пользовательского препроцессора.

    Замени логику transform() на свою предобработку признаков.
    Если нужны артефакты (скейлер, медианы и т.д.) — загружай их в on_load().
    """

    def get_name(self) -> str:
        return "my_custom_preprocessor"   # уникальный ключ

    def get_description(self) -> str:
        return "Мой пользовательский препроцессор"

    def get_version(self) -> str:
        return "1.0.0"

    def get_input_type(self) -> str:
        return RAW_FLOW   # или RAW_PACKETS / HOST_EVENTS

    def get_output_schema_id(self) -> str:
        return "my_schema_v1"   # должен совпадать с get_accepted_schema_ids() модели

    def get_feature_names(self) -> list[str]:
        return ["feature_a", "feature_b", "feature_c"]

    def on_load(self) -> None:
        """Загрузка артефактов при регистрации."""
        pass

    def transform(self, raw_input) -> PluginFeatureVector:
        """
        raw_input: NormalizedFlowEvent — сырое событие из pipeline.

        Поля события:
          raw_input.src_ip, raw_input.dst_ip, raw_input.src_port, raw_input.dst_port
          raw_input.protocol, raw_input.packet_count, raw_input.byte_count
          raw_input.duration_ms, raw_input.raw_features (dict, 71 признак)
          raw_input.raw_features_cic2023 (dict, 46 признаков, только advanced mode)
        """
        # Пример: извлекаем три простых признака
        feature_a = float(raw_input.byte_count) / max(float(raw_input.packet_count), 1)
        feature_b = float(raw_input.duration_ms) / 1000.0
        feature_c = 1.0 if raw_input.protocol == "TCP" else 0.0

        return PluginFeatureVector(
            features=[feature_a, feature_b, feature_c],
            feature_names=self.get_feature_names(),
            schema_id=self.get_output_schema_id(),
            meta={
                "event_id": raw_input.event_id,
                "src_ip":   raw_input.src_ip,
            },
        )
