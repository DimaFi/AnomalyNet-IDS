"""
PluginRegistry — реестр препроцессоров и моделей для plugin pipeline.

Хранит зарегистрированные BasePreprocessor и BaseModel по именам.
Поддерживает:
  - регистрацию builtin плагинов при старте приложения
  - динамическую загрузку пользовательских плагинов из папки plugins/
  - список активных PipelineConfig
  - сохранение пользовательских пайплайнов в JSON

Singleton: один экземпляр на всё приложение через get_registry().
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from app.plugins.base_preprocessor import BasePreprocessor
from app.plugins.base_model import BaseModel
from app.plugins.pipeline_config import PipelineConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Путь к папке пользовательских плагинов (рядом с config/)
_PLUGINS_FOLDER = Path(__file__).parent.parent.parent.parent / "plugins"
# Путь для хранения пользовательских pipeline конфигов
_USER_PIPELINES_FILE = Path(__file__).parent.parent.parent.parent / "config" / "user_pipelines.json"


class PluginRegistry:
    """
    Центральный реестр плагинов.

    preprocessors: dict имя → экземпляр BasePreprocessor
    models:        dict имя → экземпляр BaseModel
    pipelines:     dict имя → PipelineConfig (builtin + пользовательские)
    """

    def __init__(self) -> None:
        self.preprocessors: dict[str, BasePreprocessor] = {}
        self.models:        dict[str, BaseModel]        = {}
        self.pipelines:     dict[str, PipelineConfig]   = {}

    # ── Регистрация ────────────────────────────────────────────────────────────

    def register_preprocessor(self, instance: BasePreprocessor) -> None:
        name = instance.get_name()
        if name in self.preprocessors:
            logger.warning("Препроцессор '%s' уже зарегистрирован — перезаписываем", name)
        instance.on_load()
        self.preprocessors[name] = instance
        logger.info("Препроцессор зарегистрирован: %s", name)

    def register_model(self, instance: BaseModel) -> None:
        name = instance.get_name()
        if name in self.models:
            logger.warning("Модель '%s' уже зарегистрирована — перезаписываем", name)
        instance.on_load()
        self.models[name] = instance
        logger.info("Модель зарегистрирована: %s", name)

    def register_pipeline(self, config: PipelineConfig) -> None:
        errors = config.validate(self)
        if errors:
            logger.error(
                "Pipeline '%s' содержит ошибки:\n%s",
                config.name,
                "\n".join(f"  • {e}" for e in errors),
            )
        self.pipelines[config.name] = config
        logger.info("Pipeline зарегистрирован: %s (is_builtin=%s)", config.name, config.is_builtin)

    # ── Динамическая загрузка из файловой системы ──────────────────────────────

    def discover_plugins(self, folder: Path | None = None) -> int:
        """
        Сканирует папку plugins/ (или переданный folder) на Python-файлы,
        импортирует их и регистрирует все найденные BasePreprocessor/BaseModel.

        Возвращает количество успешно зарегистрированных плагинов.
        """
        target = folder or _PLUGINS_FOLDER
        if not target.exists():
            logger.info("Папка плагинов не найдена: %s — пропускаем discover", target)
            return 0

        count = 0
        for py_file in sorted(target.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            count += self._load_plugin_file(py_file)

        return count

    def _load_plugin_file(self, path: Path) -> int:
        """Импортирует один .py файл и регистрирует найденные классы. Возвращает 0 или 1."""
        module_name = f"_user_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                logger.warning("Не удалось создать spec для %s", path)
                return 0
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("Ошибка загрузки плагина %s: %s", path.name, exc)
            return 0

        registered = 0
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module_name:
                continue   # пропускаем импортированные классы
            if issubclass(obj, BasePreprocessor) and obj is not BasePreprocessor:
                try:
                    instance = obj()
                    self.register_preprocessor(instance)
                    registered += 1
                except Exception as exc:
                    logger.error("Ошибка инициализации препроцессора %s: %s", _name, exc)
            elif issubclass(obj, BaseModel) and obj is not BaseModel:
                try:
                    instance = obj()
                    self.register_model(instance)
                    registered += 1
                except Exception as exc:
                    logger.error("Ошибка инициализации модели %s: %s", _name, exc)

        return registered

    # ── Пользовательские pipeline ──────────────────────────────────────────────

    def load_user_pipelines(self, path: Path | None = None) -> int:
        """
        Загружает пользовательские PipelineConfig из JSON-файла.
        Возвращает количество загруженных конфигов.
        """
        target = path or _USER_PIPELINES_FILE
        if not target.exists():
            return 0
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            count = 0
            for item in data.get("pipelines", []):
                try:
                    cfg = PipelineConfig.from_dict(item)
                    self.register_pipeline(cfg)
                    count += 1
                except Exception as exc:
                    logger.error("Ошибка загрузки пользовательского pipeline: %s", exc)
            return count
        except Exception as exc:
            logger.error("Ошибка чтения %s: %s", target, exc)
            return 0

    def save_user_pipelines(self, path: Path | None = None) -> None:
        """Сохраняет все не-builtin pipeline в JSON-файл."""
        target = path or _USER_PIPELINES_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        user_pipelines = [
            cfg.to_dict()
            for cfg in self.pipelines.values()
            if not cfg.is_builtin
        ]
        target.write_text(
            json.dumps({"pipelines": user_pipelines}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete_pipeline(self, name: str) -> bool:
        """
        Удаляет pipeline по имени. Builtin нельзя удалить через API.
        Возвращает True если удалён.
        """
        cfg = self.pipelines.get(name)
        if cfg is None:
            return False
        if cfg.is_builtin:
            raise PermissionError(f"Pipeline '{name}' — встроенный, удаление запрещено")
        del self.pipelines[name]
        self.save_user_pipelines()
        return True

    # ── Выгрузка ───────────────────────────────────────────────────────────────

    def unload_preprocessor(self, name: str) -> bool:
        p = self.preprocessors.pop(name, None)
        if p:
            p.on_unload()
            return True
        return False

    def unload_model(self, name: str) -> bool:
        m = self.models.pop(name, None)
        if m:
            m.on_unload()
            return True
        return False


# ── Singleton ──────────────────────────────────────────────────────────────────

_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
