"""
Абстрактный базовый класс для препроцессоров плагинов.

Чтобы создать свой препроцессор — унаследуйся от BasePreprocessor
и реализуй все abstractmethod. Положи файл в папку plugins/ в корне проекта.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.plugins.contracts import PluginFeatureVector, RAW_FLOW


class BasePreprocessor(ABC):
    """
    Базовый класс препроцессора.

    Препроцессор принимает сырые данные потока (RawFlow) и возвращает
    числовой вектор признаков (PluginFeatureVector) для подачи в модель.
    """

    @abstractmethod
    def get_name(self) -> str:
        """
        Уникальное имя препроцессора, например 'cicflowmeter_71'.
        Используется как ключ в PluginRegistry — должно быть уникальным.
        """

    @abstractmethod
    def get_description(self) -> str:
        """Описание для отображения в UI."""

    @abstractmethod
    def get_version(self) -> str:
        """Версия артефактов, например '1.0.0'."""

    @abstractmethod
    def get_input_type(self) -> str:
        """
        Тип входных данных: RAW_FLOW | RAW_PACKETS | HOST_EVENTS.
        Большинство встроенных препроцессоров используют RAW_FLOW.
        """
        return RAW_FLOW

    @abstractmethod
    def get_output_schema_id(self) -> str:
        """
        Идентификатор схемы признаков которую производит этот препроцессор.
        Например: "cicflowmeter_71" или "cic_iot2023_46".
        Это ключ совместимости с моделью — модель принимает только
        схемы из своего get_accepted_schema_ids().
        """

    @abstractmethod
    def get_feature_names(self) -> list[str]:
        """
        Список имён признаков в том порядке, в котором они появляются в векторе.
        Длина должна совпадать с len(PluginFeatureVector.features).
        """

    @abstractmethod
    def transform(self, raw_input) -> PluginFeatureVector:
        """
        Основной метод преобразования.

        Принимает: RawFlow (или другой тип согласно get_input_type())
        Возвращает: PluginFeatureVector

        raw_input.data содержит dict с полями потока, включая
        raw_features (71 признак) и raw_features_cic2023 (46 признаков).
        """

    def on_load(self) -> None:
        """
        Вызывается при регистрации препроцессора.
        Загрузи здесь артефакты (медианы, скейлеры и т.д.) если нужно.
        """

    def on_unload(self) -> None:
        """Вызывается при выгрузке препроцессора из реестра."""

    def get_metadata(self) -> dict:
        """Метаданные для API /api/plugins/preprocessors."""
        return {
            "name":            self.get_name(),
            "description":     self.get_description(),
            "version":         self.get_version(),
            "input_type":      self.get_input_type(),
            "output_schema_id": self.get_output_schema_id(),
            "feature_count":   len(self.get_feature_names()),
            "feature_names":   self.get_feature_names(),
            "is_builtin":      False,
        }
