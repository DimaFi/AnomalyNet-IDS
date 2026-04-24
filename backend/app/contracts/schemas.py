from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ThemeMode = Literal["dark", "light", "gray"]
LanguageCode = Literal["ru", "en"]
RunMode = Literal["mock", "windows_stub", "linux_stub", "linux_live"]
StatusLevel = Literal["idle", "active", "warning", "error"]
VerdictLabel = Literal["normal", "warning", "anomaly"]
DetectionMode = Literal["simple", "advanced"]


class AppSettings(BaseModel):
    language: LanguageCode = "ru"
    theme: ThemeMode = "dark"
    run_mode: RunMode = "mock"
    retention_days: int = Field(default=14, ge=1, le=30)
    active_model_id: str = "mock-default"
    capture_enabled: bool = True
    stream_autostart: bool = True
    # Network capture — single or multi-interface (interface_names takes precedence)
    interface_name: str = "eth0"
    interface_names: list[str] = Field(default_factory=list)
    # CatBoost model configuration
    catboost_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    auto_block: bool = False
    # "anomaly" = блокировать только аномалии (score≥0.85)
    # "warning"  = блокировать и предупреждения, и аномалии
    auto_block_level: Literal["anomaly", "warning"] = "anomaly"
    # Автоматически снимать блокировку после cooldown минут
    auto_unblock: bool = False
    auto_unblock_cooldown_min: int = Field(default=10, ge=1, le=120)
    # IPs that are never auto-blocked (whitelist)
    whitelist_ips: list[str] = Field(default_factory=list)
    # Detection mode (affects capture adapter: whether to compute 46 CIC-IoT-2023 features)
    detection_mode: DetectionMode = "simple"
    # Model packages directory (contains subfolders with metadata.json + model.cbm)
    models_dir: str = ""
    # Auto-download official AnomalyNet models on first run
    auto_download_models: bool = True
    # Auto-update models via git pull on startup
    auto_update_models: bool = False


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
    # Raw CICFlowMeter-style features (71); populated by real capture adapters, None in mock
    raw_features: dict[str, float] | None = Field(default=None, exclude=True)
    # Raw CIC IoT 2023 features (46); populated only in advanced detection mode
    raw_features_cic2023: dict[str, float] | None = Field(default=None, exclude=True)
    # Attack class name from multiclass model ("DoS", "DDoS", etc.); None for binary/mock
    attack_class: str | None = None


class FeatureVector(BaseModel):
    event_id: str
    contract_version: str
    profile_name: str
    values: dict[str, float | int | str]
    # Secondary feature set for cascade advanced mode (46 CIC2023 features); None otherwise
    secondary_values: dict[str, float] | None = None
    # Source IP — populated by preprocessing pipelines for routing in CascadeRoutedAdapter
    src_ip: str | None = None


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
    device_type: str | None = None       # "pc_windows", "iot_camera", etc.
    device_name: str | None = None       # display_name()
    pipeline_used: str | None = None     # "advanced", "general_network"


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
    interface_names: list[str] = Field(default_factory=list)
    catboost_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    auto_block: bool = False
    auto_block_level: Literal["anomaly", "warning"] = "anomaly"
    auto_unblock: bool = False
    auto_unblock_cooldown_min: int = Field(default=10, ge=1, le=120)
    whitelist_ips: list[str] = Field(default_factory=list)
    detection_mode: DetectionMode = "simple"
    models_dir: str = ""
    auto_download_models: bool = True
    auto_update_models: bool = False


class ModelPreset(BaseModel):
    id: str
    name: str
    description: str
    icon: str = ""
    active_model_id: str
    run_mode: RunMode
    detection_mode: DetectionMode = "simple"


class ModelPresetsRegistry(BaseModel):
    presets: list[ModelPreset]


class BlockRequest(BaseModel):
    ip_address: str
    event_id: str | None = None


class BlockResponse(BaseModel):
    ip_address: str
    blocked: bool
    message: str = ""


class AttackClassStats(BaseModel):
    count: int
    last_seen: datetime | None = None


class DebugStats(BaseModel):
    """Detailed statistics for developer/debug view."""
    uptime_events_total: int
    events_by_label: dict[str, int]           # normal / warning / anomaly
    events_by_protocol: dict[str, int]         # TCP / UDP / ICMP / OTHER
    events_by_attack_class: dict[str, int]     # DoS, DDoS, Recon, ...
    top_src_ips: dict[str, int]                # src_ip → count (top 10)
    top_dst_ports: dict[str, int]              # dst_port → count (top 10)
    avg_score: float
    max_score: float
    detection_mode: str
    active_model_id: str
    interface: str
    capture_status: str
