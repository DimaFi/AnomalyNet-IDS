"""
Абстрактный базовый класс для моделей плагинов.

Чтобы создать свою модель — унаследуйся от BaseModel
и реализуй все abstractmethod. Положи файл в папку plugins/ в корне проекта.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.plugins.contracts import PluginFeatureVector, PluginVerdict


class BaseModel(ABC):
    """
    Базовый класс модели детектора.

    Модель принимает числовой вектор признаков (PluginFeatureVector)
    и возвращает вердикт (PluginVerdict).
    """

    @abstractmethod
    def get_name(self) -> str:
        """
        Уникальное имя модели, например 'catboost_stage1'.
        Используется как ключ в PluginRegistry.
        """

    @abstractmethod
    def get_description(self) -> str:
        """Описание для UI."""

    @abstractmethod
    def get_version(self) -> str:
        """Версия модели, например '1.0.0'."""

    @abstractmethod
    def get_accepted_schema_ids(self) -> list[str]:
        """
        Список schema_id которые эта модель принимает.
        Например: ["cicflowmeter_71"] или ["cic_iot2023_46"].

        Используется для проверки совместимости с препроцессором.
        Если список пуст — модель принимает любой вектор (не рекомендуется).
        """

    @abstractmethod
    def get_output_classes(self) -> list[str]:
        """
        Классы которые модель умеет предсказывать.
        Например: ["Benign", "Attack"] для Stage1
        или: ["DoS", "DDoS", "Mirai", "Recon", ...] для Stage3.
        """

    @abstractmethod
    def predict(self, features: PluginFeatureVector) -> PluginVerdict:
        """
        Основной метод предсказания.

        Принимает PluginFeatureVector.
        ВАЖНО: перед predict проверь совместимость:
            if features.schema_id not in self.get_accepted_schema_ids():
                raise ValueError(...)
        Возвращает PluginVerdict.
        """

    def on_load(self) -> None:
        """
        Вызывается при регистрации модели.
        Загрузи здесь .cbm файл модели и вспомогательные артефакты.
        """

    def on_unload(self) -> None:
        """Вызывается при выгрузке модели из реестра."""

    def get_metadata(self) -> dict:
        """Метаданные для API /api/plugins/models."""
        return {
            "name":                self.get_name(),
            "description":         self.get_description(),
            "version":             self.get_version(),
            "accepted_schema_ids": self.get_accepted_schema_ids(),
            "output_classes":      self.get_output_classes(),
            "is_builtin":          False,
        }

    def check_compatibility(self, schema_id: str) -> tuple[bool, str]:
        """
        Проверяет совместимость с указанной схемой признаков.
        Возвращает (compatible: bool, reason: str).
        """
        accepted = self.get_accepted_schema_ids()
        if not accepted:
            return True, "Модель принимает любую схему признаков"
        if schema_id in accepted:
            return True, ""
        return False, (
            f"Модель '{self.get_name()}' ожидает схему из {accepted}, "
            f"получила '{schema_id}'"
        )
