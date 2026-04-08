from __future__ import annotations

from fastapi import Request

from app.pipeline.service import PipelineService


def get_pipeline_service(request: Request) -> PipelineService:
    return request.app.state.pipeline_service

