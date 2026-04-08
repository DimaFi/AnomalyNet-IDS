from __future__ import annotations

from pathlib import Path

from app.contracts.schemas import AppSettings, ModelDescriptor
from app.preprocess.pipeline import MockPreprocessingPipeline


def build_preprocessing_pipeline(descriptor: ModelDescriptor, settings: AppSettings):
    """Returns the appropriate preprocessing pipeline based on the model descriptor."""
    if descriptor.is_mock:
        return MockPreprocessingPipeline()

    if descriptor.profile_name == "catboost_iot_71":
        from app.preprocess.catboost_pipeline import CatBoostPreprocessingPipeline
        artifacts_dir = Path(settings.preprocessing_artifacts_dir)
        return CatBoostPreprocessingPipeline(artifacts_dir=artifacts_dir)

    raise ValueError(
        f"Unknown model profile '{descriptor.profile_name}' "
        f"for model_id='{descriptor.model_id}'"
    )
