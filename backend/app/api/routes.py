from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.contracts.schemas import HealthResponse, ModelsRegistry, SettingsUpdate, StreamSnapshot
from app.dependencies import get_pipeline_service
from app.pipeline.service import PipelineService
from app.preprocess.contracts import DEFAULT_CONTRACT_VERSION


router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def get_health(service: PipelineService = Depends(get_pipeline_service)) -> HealthResponse:
    return HealthResponse(
        service="traffic-analysis-local-api",
        status=service.status,
        mode=service.settings.run_mode,
        active_model_id=service.settings.active_model_id,
        retention_days=service.settings.retention_days,
        contract_version=DEFAULT_CONTRACT_VERSION,
    )


@router.get("/settings")
def get_settings(service: PipelineService = Depends(get_pipeline_service)):
    return service.settings


@router.put("/settings")
def update_settings(payload: SettingsUpdate, service: PipelineService = Depends(get_pipeline_service)):
    return service.update_settings(payload)


@router.get("/models", response_model=ModelsRegistry)
def get_models(service: PipelineService = Depends(get_pipeline_service)) -> ModelsRegistry:
    return service.models


@router.post("/models/select", response_model=ModelsRegistry)
def select_model(payload: dict[str, str], service: PipelineService = Depends(get_pipeline_service)) -> ModelsRegistry:
    model_id = payload.get("model_id")
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id is required")
    if model_id not in {item.model_id for item in service.models.items}:
        raise HTTPException(status_code=404, detail="model not found")
    return service.select_model(model_id)


@router.get("/stream/snapshot", response_model=StreamSnapshot)
def get_snapshot(service: PipelineService = Depends(get_pipeline_service)) -> StreamSnapshot:
    return service.snapshot()


@router.get("/history")
def get_history(limit: int = 50, service: PipelineService = Depends(get_pipeline_service)):
    return service.history(limit=limit)

