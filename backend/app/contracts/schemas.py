from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ThemeMode = Literal["dark", "light"]
LanguageCode = Literal["ru", "en"]
RunMode = Literal["mock", "windows_stub", "linux_stub", "linux_live"]
StatusLevel = Literal["idle", "active", "warning", "error"]
VerdictLabel = Literal["normal", "warning", "anomaly"]


class AppSettings(BaseModel):
    language: LanguageCode = "ru"
    theme: ThemeMode = "dark"
    run_mode: RunMode = "mock"
    retention_days: int = Field(default=14, ge=1, le=30)
    active_model_id: str = "mock-default"
    capture_enabled: bool = True
    stream_autostart: bool = True
    # Network capture
    interface_name: str = "eth0"
    # CatBoost model configuration
    catboost_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    catboost_model_dir: str = ""
    preprocessing_artifacts_dir: str = ""
    auto_block: bool = False


class ModelDescriptor(BaseModel):
    model_id: str
    display_name: str
    version: str
    provider: str
    contract_version: str
    profile_name: str
    artifact_path: str
    supported_modes: list[RunMode]
    is_mock: bool = False
    description: str
    status: StatusLevel = "idle"


class ModelsRegistry(BaseModel):
    active_model_id: str
    items: list[ModelDescriptor]


class NormalizedFlowEvent(BaseModel):
    event_id: str
    timestamp: datetime
    source: str
    direction: Literal["inbound", "outbound", "lateral"]
    protocol: Literal["TCP", "UDP", "ICMP", "OTHER"]
    src_ip: str
    dst_ip: str
    src_port: int = Field(ge=0, le=65535)
    dst_port: int = Field(ge=0, le=65535)
    packet_count: int = Field(ge=1)
    byte_count: int = Field(ge=1)
    duration_ms: int = Field(ge=1)
    risk_hint: float = Field(ge=0.0, le=1.0)
    # Raw CICFlowMeter-style features; populated by real capture adapters, None in mock mode
    raw_features: dict[str, float] | None = Field(default=None, exclude=True)
    # Attack class name from multiclass model ("DoS", "DDoS", etc.); None for binary/mock
    attack_class: str | None = None


class FeatureVector(BaseModel):
    event_id: str
    contract_version: str
    profile_name: str
    values: dict[str, float | int | str]


class InferenceResult(BaseModel):
    event_id: str
    label: VerdictLabel
    score: float = Field(ge=0.0, le=1.0)
    reason: str
    model_id: str
    attack_class: str | None = None   # "DoS", "DDoS", etc. — только в multiclass


class AlertRecord(BaseModel):
    alert_id: str
    timestamp: datetime
    level: VerdictLabel
    title: str
    details: str
    event_id: str


class PipelineEvent(BaseModel):
    event: NormalizedFlowEvent
    features: FeatureVector
    inference: InferenceResult
    alert: AlertRecord | None = None


class HealthResponse(BaseModel):
    service: str
    status: StatusLevel
    mode: RunMode
    active_model_id: str
    retention_days: int
    contract_version: str


class StreamSnapshot(BaseModel):
    status: StatusLevel
    queue_size: int
    items: list[PipelineEvent]


class SettingsUpdate(BaseModel):
    language: LanguageCode
    theme: ThemeMode
    run_mode: RunMode
    retention_days: int = Field(ge=1, le=30)
    active_model_id: str
    capture_enabled: bool
    stream_autostart: bool
    interface_name: str = "eth0"
    catboost_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    catboost_model_dir: str = ""
    preprocessing_artifacts_dir: str = ""
    auto_block: bool = False


class BlockRequest(BaseModel):
    ip_address: str
    event_id: str | None = None


class BlockResponse(BaseModel):
    ip_address: str
    blocked: bool
    message: str = ""
