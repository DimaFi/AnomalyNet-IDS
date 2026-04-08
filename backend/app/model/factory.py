from __future__ import annotations

from pathlib import Path

from app.contracts.schemas import AppSettings, ModelDescriptor
from app.model.adapters import MockModelAdapter


def build_model_adapter(descriptor: ModelDescriptor, settings: AppSettings):
    """Returns the appropriate model adapter based on the model descriptor."""
    if descriptor.is_mock:
        return MockModelAdapter()

    if descriptor.profile_name == "catboost_iot_71":
        from app.model.catboost_adapter import CatBoostModelAdapter
        model_dir = Path(settings.catboost_model_dir)
        return CatBoostModelAdapter(
            model_dir=model_dir,
            model_id=descriptor.model_id,
            threshold=settings.catboost_threshold,
        )

    raise ValueError(
        f"Unknown model profile '{descriptor.profile_name}' "
        f"for model_id='{descriptor.model_id}'"
    )
