from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.contracts.schemas import (
    AppSettings, DebugStats, HealthResponse, ModelPresetsRegistry, ModelsRegistry,
    NormalizedFlowEvent, SettingsUpdate, StreamSnapshot,
)
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
def get_history(
    limit: int = 100,
    offset: int = 0,
    service: PipelineService = Depends(get_pipeline_service),
):
    items = service.history(limit=limit, offset=offset)
    return {
        "total": len(service._recent_items),
        "offset": offset,
        "limit": limit,
        "items": [e.model_dump(mode="json") for e in items],
    }


@router.get("/model-presets", response_model=ModelPresetsRegistry)
def get_model_presets(service: PipelineService = Depends(get_pipeline_service)) -> ModelPresetsRegistry:
    """Returns all available model presets with resolved paths."""
    return service.get_presets()


@router.get("/debug/stats", response_model=DebugStats)
def get_debug_stats(service: PipelineService = Depends(get_pipeline_service)) -> DebugStats:
    """Detailed detection statistics — for developer/debug view and VPS testing."""
    return service.debug_stats()


@router.get("/export")
def export_data(
    limit: int = 200,
    service: PipelineService = Depends(get_pipeline_service)
):
    """Export structured detection report: summary stats + recent events history.
    Useful for thesis/research data collection after a test session."""
    stats = service.debug_stats()
    history = service.history(limit=limit)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "summary": stats.model_dump(),
        "events_count": len(history),
        "events": [e.model_dump(mode="json") for e in history],
    }


class InferRow(BaseModel):
    raw_features: dict[str, Any]
    raw_features_cic2023: dict[str, Any] | None = None
    src_ip: str = "0.0.0.0"
    dst_ip: str = "0.0.0.0"
    src_port: int = 0
    dst_port: int = 80
    protocol: str = "TCP"
    packet_count: int = 10
    byte_count: int = 500
    duration_ms: int = 100
    true_label: str | None = None   # ground truth for accuracy measurement


class InferBatchRequest(BaseModel):
    rows: list[InferRow]


@router.post("/debug/infer")
def debug_infer(
    payload: InferBatchRequest,
    service: PipelineService = Depends(get_pipeline_service),
):
    """Batch inference on pre-computed features — bypasses capture layer.
    Used for offline accuracy testing: send test dataset rows, get predictions back."""
    preprocess, model = service._get_pipeline_and_model()
    results = []
    for row in payload.rows:
        try:
            event = NormalizedFlowEvent(
                event_id=str(uuid4()),
                timestamp=datetime.now(timezone.utc),
                source="debug/infer",
                direction="inbound",
                protocol=row.protocol,
                src_ip=row.src_ip,
                dst_ip=row.dst_ip,
                src_port=row.src_port,
                dst_port=row.dst_port,
                packet_count=row.packet_count,
                byte_count=row.byte_count,
                duration_ms=row.duration_ms,
                risk_hint=0.0,
                raw_features=row.raw_features,
                raw_features_cic2023=row.raw_features_cic2023,
            )
            features = preprocess.transform(event)
            inference = model.infer(features)
            results.append({
                "predicted_label": inference.label,
                "predicted_class": inference.attack_class,
                "score": inference.score,
                "true_label": row.true_label,
                "correct": (row.true_label == inference.attack_class) if row.true_label else None,
            })
        except Exception as e:
            results.append({"error": str(e), "true_label": row.true_label})
    return {"count": len(results), "results": results}


@router.get("/fs/ls")
def fs_ls(path: str) -> dict:
    """Returns directory listing for a given absolute path (read-only, for UI inspection)."""
    import os
    from pathlib import Path as _P
    p = _P(path)
    if not p.exists():
        return {"path": str(p), "exists": False, "entries": []}
    if not p.is_dir():
        stat = p.stat()
        return {"path": str(p), "exists": True, "is_file": True,
                "size_bytes": stat.st_size, "entries": []}
    entries = []
    try:
        for item in sorted(p.iterdir()):
            try:
                st = item.stat()
                entries.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size_bytes": st.st_size if item.is_file() else None,
                })
            except OSError:
                pass
    except PermissionError as e:
        return {"path": str(p), "exists": True, "error": str(e), "entries": []}
    return {"path": str(p), "exists": True, "entries": entries}


@router.post("/model-presets/apply/{preset_id}", response_model=AppSettings)
def apply_model_preset(
    preset_id: str,
    service: PipelineService = Depends(get_pipeline_service),
) -> AppSettings:
    """Applies a preset — updates settings and switches active model in one request."""
    presets = service.get_presets()
    preset = next((p for p in presets.presets if p.id == preset_id), None)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
    return service.apply_preset(preset)

