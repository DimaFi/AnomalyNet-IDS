from __future__ import annotations

from pathlib import Path

from app.contracts.schemas import AppSettings, ModelDescriptor
from app.model.adapters import MockModelAdapter


def build_model_adapter(descriptor: ModelDescriptor, settings: AppSettings):
    """Returns the appropriate model adapter based on the model descriptor."""
    if descriptor.is_mock:
        return MockModelAdapter()

    profile = descriptor.profile_name

    # Stage1 binary
    if profile == "catboost_iot_71":
        from app.model.catboost_adapter import CatBoostModelAdapter
        return CatBoostModelAdapter(
            model_dir=Path(settings.catboost_model_dir),
            model_id=descriptor.model_id,
            threshold=settings.catboost_threshold,
        )

    # Stage2 multiclass (standalone, without binary gate)
    if profile == "catboost_iot_71_mc":
        from app.model.catboost_adapter import CatBoostModelAdapter
        # Secondary model dir if set, else primary
        model_dir = (
            Path(settings.catboost_secondary_model_dir)
            if settings.catboost_secondary_model_dir
            else Path(settings.catboost_model_dir)
        )
        return CatBoostModelAdapter(
            model_dir=model_dir,
            model_id=descriptor.model_id,
            threshold=settings.catboost_threshold,
        )

    # Cascade Simple: Stage1 (binary) → Stage2 (multiclass), both 71 features
    if profile == "catboost_cascade_simple":
        from app.model.cascade_adapter import CascadeSimpleAdapter
        return CascadeSimpleAdapter(
            stage1_dir=Path(settings.catboost_model_dir),
            stage2_dir=Path(settings.catboost_secondary_model_dir),
            model_id=descriptor.model_id,
            threshold=settings.catboost_threshold,
        )

    # Cascade Advanced: Stage1 (binary, 71) → Stage3/Stage4 (multiclass, 46 CIC2023)
    if profile == "catboost_cascade_advanced":
        from app.model.cascade_adapter import CascadeAdvancedAdapter
        return CascadeAdvancedAdapter(
            stage1_dir=Path(settings.catboost_model_dir),
            stage3_dir=Path(settings.catboost_secondary_model_dir),
            model_id=descriptor.model_id,
            threshold=settings.catboost_threshold,
        )

    # Standalone Stage3/Stage4: 46 CIC IoT 2023 features, direct multiclass (no binary gate)
    if profile == "catboost_iot_46_cic2023":
        from app.model.catboost_adapter import CatBoostModelAdapter
        model_dir = (
            Path(settings.catboost_secondary_model_dir)
            if settings.catboost_secondary_model_dir
            else Path(settings.catboost_model_dir)
        )
        return CatBoostModelAdapter(
            model_dir=model_dir,
            model_id=descriptor.model_id,
            threshold=settings.catboost_threshold,
        )

    raise ValueError(
        f"Unknown model profile '{profile}' "
        f"for model_id='{descriptor.model_id}'"
    )
