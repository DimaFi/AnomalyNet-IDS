"""
Builtin pipeline presets и инициализация registry.

build_builtin_registry(settings) — создаёт PluginRegistry,
регистрирует builtin препроцессоры, модели и три preset-пайплайна.

Вызывается из main.py один раз при старте приложения.
Если пути к моделям не заданы в settings — builtin плагины не регистрируются
(graceful degradation: работает mock-режим и пользовательские плагины).
"""
from __future__ import annotations

import logging

from app.contracts.schemas import AppSettings
from app.plugins.pipeline_config import PipelineConfig, StageConfig
from app.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


# ── Pipeline preset configs (не зависят от путей, только имена плагинов) ─────

def _make_preset_fast() -> PipelineConfig:
    """
    FAST: Только Stage1 (бинарный gate без классификации).
    Минимальная задержка — подходит для высоконагруженных сетей.
    """
    return PipelineConfig(
        name="fast",
        description="Быстрый детектор: Stage1 binary gate без классификации типа атаки",
        entry_stage="stage1",
        stages={
            "stage1": StageConfig(
                preprocessor_name="cicflowmeter_71",
                model_name="builtin_stage1_binary",
                threshold=0.70,
                is_gate=False,
                next_stage=None,
            ),
        },
        is_builtin=True,
    )


def _make_preset_simple() -> PipelineConfig:
    """
    SIMPLE: Stage1 (binary gate) → Stage2 (8-классовый, 71 признак).
    Оба этапа используют одинаковые 71 CICFlowMeter признаков.
    """
    return PipelineConfig(
        name="simple",
        description="Simple cascade: Stage1 binary + Stage2 multiclass (71 признаков, 8 классов)",
        entry_stage="stage1",
        stages={
            "stage1": StageConfig(
                preprocessor_name="cicflowmeter_71",
                model_name="builtin_stage1_binary",
                threshold=0.70,
                is_gate=True,
                next_stage="stage2",
            ),
            "stage2": StageConfig(
                preprocessor_name="cicflowmeter_71",
                model_name="builtin_stage2_multiclass",
                threshold=0.70,
                is_gate=False,
                next_stage=None,
            ),
        },
        is_builtin=True,
    )


def _make_preset_advanced() -> PipelineConfig:
    """
    ADVANCED: Stage1 (binary gate, 71 признак) → Stage3 (46 CIC IoT 2023 признаков).
    Stage3 — Macro F1=0.819, превосходит Stage2 на IoT-трафике.
    Требует detection_mode='advanced' (raw_features_cic2023 в событиях).
    """
    return PipelineConfig(
        name="advanced",
        description="Advanced cascade: Stage1 binary + Stage3 IoT2023 (46 признаков, Macro F1=0.819)",
        entry_stage="stage1",
        stages={
            "stage1": StageConfig(
                preprocessor_name="cicflowmeter_71",
                model_name="builtin_stage1_binary",
                threshold=0.70,
                is_gate=True,
                next_stage="stage3",
            ),
            "stage3": StageConfig(
                preprocessor_name="cic_iot2023_46",
                model_name="builtin_stage3_iot2023",
                threshold=0.70,
                is_gate=False,
                next_stage=None,
            ),
        },
        is_builtin=True,
    )


# ── Инициализация ─────────────────────────────────────────────────────────────

def build_builtin_registry(settings: AppSettings) -> PluginRegistry:
    """
    Создаёт и наполняет PluginRegistry builtin плагинами.

    Регистрирует только те плагины, для которых заданы пути в settings.
    Graceful: если путь не задан или папка не существует — плагин пропускается,
    приложение продолжает работать в mock/ограниченном режиме.
    """
    from app.plugins.registry import get_registry
    registry = get_registry()

    primary_arts  = settings.preprocessing_artifacts_dir
    secondary_arts = settings.catboost_secondary_artifacts_dir
    primary_model  = settings.catboost_model_dir
    secondary_model = settings.catboost_secondary_model_dir

    threshold = settings.catboost_threshold

    # ── Препроцессоры ──────────────────────────────────────────────────────────
    if primary_arts:
        try:
            from app.plugins.builtin.preprocessor_cicflowmeter71 import (
                BuiltinCicFlowMeter71Preprocessor,
            )
            registry.register_preprocessor(
                BuiltinCicFlowMeter71Preprocessor(primary_arts)
            )
        except Exception as exc:
            logger.warning("Не удалось зарегистрировать cicflowmeter_71 препроцессор: %s", exc)

    if secondary_arts:
        try:
            from app.plugins.builtin.preprocessor_cic_iot2023_46 import (
                BuiltinCicIot2023_46Preprocessor,
            )
            registry.register_preprocessor(
                BuiltinCicIot2023_46Preprocessor(secondary_arts)
            )
        except Exception as exc:
            logger.warning("Не удалось зарегистрировать cic_iot2023_46 препроцессор: %s", exc)

    if primary_arts and secondary_arts:
        try:
            from app.plugins.builtin.preprocessor_cascade_dual import (
                BuiltinCascadeDualPreprocessor,
            )
            registry.register_preprocessor(
                BuiltinCascadeDualPreprocessor(primary_arts, secondary_arts)
            )
        except Exception as exc:
            logger.warning("Не удалось зарегистрировать cascade_dual препроцессор: %s", exc)

    # ── Модели ────────────────────────────────────────────────────────────────
    if primary_model:
        try:
            from app.plugins.builtin.model_stage1 import BuiltinStage1Model
            registry.register_model(BuiltinStage1Model(primary_model, threshold))
        except Exception as exc:
            logger.warning("Не удалось зарегистрировать Stage1 модель: %s", exc)

    if secondary_model:
        try:
            from app.plugins.builtin.model_stage2 import BuiltinStage2Model
            registry.register_model(BuiltinStage2Model(secondary_model, threshold))
        except Exception as exc:
            logger.warning("Не удалось зарегистрировать Stage2 модель: %s", exc)

        try:
            from app.plugins.builtin.model_stage3 import BuiltinStage3Model
            registry.register_model(BuiltinStage3Model(secondary_model, threshold))
        except Exception as exc:
            logger.warning("Не удалось зарегистрировать Stage3 модель: %s", exc)

    # ── Preset pipelines ──────────────────────────────────────────────────────
    for preset_fn in (_make_preset_fast, _make_preset_simple, _make_preset_advanced):
        try:
            registry.register_pipeline(preset_fn())
        except Exception as exc:
            logger.warning("Ошибка регистрации preset pipeline: %s", exc)

    # ── Загрузить пользовательские пайплайны из config/user_pipelines.json ────
    registry.load_user_pipelines()

    # ── Discover плагины из папки plugins/ ───────────────────────────────────
    n = registry.discover_plugins()
    if n:
        logger.info("Загружено %d пользовательских плагинов из plugins/", n)

    return registry
