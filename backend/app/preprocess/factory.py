from __future__ import annotations

from pathlib import Path

from app.contracts.schemas import AppSettings, ModelDescriptor
from app.preprocess.pipeline import MockPreprocessingPipeline


def build_preprocessing_pipeline(descriptor: ModelDescriptor, settings: AppSettings):
    """Returns the appropriate preprocessing pipeline based on the model descriptor."""
    if descriptor.is_mock:
        return MockPreprocessingPipeline()

    profile = descriptor.profile_name

    # Stage1 binary OR Stage2 multiclass (both use 71 CICFlowMeter features)
    if profile in ("catboost_iot_71", "catboost_iot_71_mc"):
        from app.preprocess.catboost_pipeline import CatBoostPreprocessingPipeline
        artifacts_dir = Path(settings.preprocessing_artifacts_dir)
        return CatBoostPreprocessingPipeline(artifacts_dir=artifacts_dir)

    # Cascade Simple: Stage1 + Stage2, single feature space (71 features)
    if profile == "catboost_cascade_simple":
        from app.preprocess.catboost_pipeline import CatBoostPreprocessingPipeline
        artifacts_dir = Path(settings.preprocessing_artifacts_dir)
        return CatBoostPreprocessingPipeline(artifacts_dir=artifacts_dir)

    # Cascade Advanced: Stage1 (71 features) + Stage3 (46 features)
    if profile == "catboost_cascade_advanced":
        from app.preprocess.cascade_pipeline import CascadeAdvancedPipeline
        primary_dir = Path(settings.preprocessing_artifacts_dir)
        # Secondary artifacts: use explicit dir if set, else fall back to primary
        if settings.catboost_secondary_artifacts_dir:
            secondary_dir = Path(settings.catboost_secondary_artifacts_dir)
        else:
            secondary_dir = primary_dir
        return CascadeAdvancedPipeline(
            primary_artifacts_dir=primary_dir,
            secondary_artifacts_dir=secondary_dir,
        )

    raise ValueError(
        f"Unknown model profile '{profile}' "
        f"for model_id='{descriptor.model_id}'"
    )
