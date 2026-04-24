from __future__ import annotations

from fastapi import Request

from app.pipeline.service import PipelineService


def get_pipeline_service(request: Request) -> PipelineService:
    return request.app.state.pipeline_service


def get_device_tracker(request: Request):  # noqa: ANN201
    from app.discovery.tracker import DeviceTracker
    return request.app.state.device_tracker

