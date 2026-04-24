"""
Builtin pipeline presets and registry initialisation.

build_builtin_registry(settings) — scans models_dir, registers all model
packages found there, then adds named pipeline presets that reference the
known AnomalyNet-ml package IDs.  If a package is missing (models not
downloaded yet) the preset is simply skipped — graceful degradation.

Called from main.py at startup and from service.py on settings change.
"""
from __future__ import annotations

import logging

from app.contracts.schemas import AppSettings
from app.plugins.pipeline_config import PipelineConfig, StageConfig
from app.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


# ── Known AnomalyNet-ml package IDs (must match metadata.json "id" field) ────

_IOT_BINARY     = "anomalynet-iot-binary"
_IOT_MC         = "anomalynet-iot-multiclass"
_IOT_ADVANCED   = "anomalynet-iot-advanced"
_GEN_BINARY     = "anomalynet-general-binary"
_GEN_MC         = "anomalynet-general-multiclass"


def _preproc(pkg_id: str) -> str:
    return f"preproc_dyn_{pkg_id}"


def _model(pkg_id: str) -> str:
    return f"model_dyn_{pkg_id}"


def _make_named_presets(registered_ids: set[str]) -> list[PipelineConfig]:
    """
    Build the well-known named pipeline presets (fast / simple / advanced /
    general_network / auto) only when the required packages are available.
    """
    presets: list[PipelineConfig] = []

    # ── fast: IoT binary gate, no classification ───────────────────────────
    if _IOT_BINARY in registered_ids:
        presets.append(PipelineConfig(
            name="fast",
            description="Быстрый детектор: бинарный gate без классификации типа атаки",
            entry_stage="stage1",
            stages={
                "stage1": StageConfig(
                    preprocessor_name=_preproc(_IOT_BINARY),
                    model_name=_model(_IOT_BINARY),
                    threshold=0.70,
                    is_gate=False,
                    next_stage=None,
                ),
            },
            is_builtin=True,
        ))

    # ── simple: IoT binary → IoT multiclass ───────────────────────────────
    if _IOT_BINARY in registered_ids and _IOT_MC in registered_ids:
        presets.append(PipelineConfig(
            name="simple",
            description="Simple cascade: IoT бинарный + 8-классовый (71 признак)",
            entry_stage="stage1",
            stages={
                "stage1": StageConfig(
                    preprocessor_name=_preproc(_IOT_BINARY),
                    model_name=_model(_IOT_BINARY),
                    threshold=0.70,
                    is_gate=True,
                    next_stage="stage2",
                ),
                "stage2": StageConfig(
                    preprocessor_name=_preproc(_IOT_MC),
                    model_name=_model(_IOT_MC),
                    threshold=0.70,
                    is_gate=False,
                    next_stage=None,
                ),
            },
            is_builtin=True,
        ))

    # ── advanced: IoT binary → IoT advanced (46-feature CIC2023) ──────────
    if _IOT_BINARY in registered_ids and _IOT_ADVANCED in registered_ids:
        presets.append(PipelineConfig(
            name="advanced",
            description="Advanced cascade: IoT бинарный + Stage3 IoT2023 (46 признаков, Macro F1=0.819)",
            entry_stage="stage1",
            stages={
                "stage1": StageConfig(
                    preprocessor_name=_preproc(_IOT_BINARY),
                    model_name=_model(_IOT_BINARY),
                    threshold=0.70,
                    is_gate=True,
                    next_stage="stage3",
                ),
                "stage3": StageConfig(
                    preprocessor_name=_preproc(_IOT_ADVANCED),
                    model_name=_model(_IOT_ADVANCED),
                    threshold=0.70,
                    is_gate=False,
                    next_stage=None,
                ),
            },
            is_builtin=True,
        ))

    # ── general_network: General binary → General multiclass ──────────────
    if _GEN_BINARY in registered_ids and _GEN_MC in registered_ids:
        presets.append(PipelineConfig(
            name="general_network",
            description="General Network IDS: бинарный + 7-классовый (CICIDS 2017, ПК/домашние сети)",
            entry_stage="stage1",
            stages={
                "stage1": StageConfig(
                    preprocessor_name=_preproc(_GEN_BINARY),
                    model_name=_model(_GEN_BINARY),
                    threshold=0.41,
                    is_gate=True,
                    next_stage="stage2",
                ),
                "stage2": StageConfig(
                    preprocessor_name=_preproc(_GEN_MC),
                    model_name=_model(_GEN_MC),
                    threshold=0.50,
                    is_gate=False,
                    next_stage=None,
                ),
            },
            is_builtin=True,
        ))

    # ── auto: device-aware routing (no stages — handled by service.py) ────
    presets.append(PipelineConfig(
        name="auto",
        description=(
            "Авто: IoT устройства → Advanced IoT; ПК/телефоны → General Network. "
            "Маршрутизация по типу устройства из карты сети."
        ),
        entry_stage="__auto__",
        stages={},
        is_builtin=True,
    ))

    return presets


# ── Main entry point ──────────────────────────────────────────────────────────

def build_builtin_registry(settings: AppSettings) -> PluginRegistry:
    """
    Scan models_dir, register all valid model packages, then register named
    pipeline presets for the known AnomalyNet-ml packages that are present.

    Graceful: if models_dir is empty or a package is missing, the
    corresponding preset is simply not registered.  Mock-mode still works.
    """
    from app.plugins.registry import get_registry
    registry = get_registry()

    registered_ids: set[str] = set()

    if settings.models_dir:
        try:
            from app.models_manager.package import scan_models_dir
            from app.models_manager.dynamic_registry import register_packages
            packages = scan_models_dir(settings.models_dir)
            register_packages(packages, registry, settings.catboost_threshold)
            # Track only packages that were ACTUALLY registered (preprocessor + model both present)
            registered_ids = {
                p.id for p in packages
                if f"preproc_dyn_{p.id}" in registry.preprocessors
                and f"model_dyn_{p.id}" in registry.models
            }
            logger.info(
                "Registered %d/%d model packages from %s",
                len(registered_ids),
                len(packages),
                settings.models_dir,
            )
        except Exception as exc:
            logger.warning("Failed to load model packages from %s: %s", settings.models_dir, exc)
    else:
        logger.info(
            "models_dir is not set — no model packages loaded. "
            "Set models_dir in settings or use mock mode."
        )

    # Register named presets
    for preset in _make_named_presets(registered_ids):
        try:
            registry.register_pipeline(preset)
        except Exception as exc:
            logger.warning("Error registering preset %r: %s", preset.name, exc)

    # Load user-defined pipelines and external plugins
    registry.load_user_pipelines()
    n = registry.discover_plugins()
    if n:
        logger.info("Loaded %d user plugins from plugins/", n)

    return registry
