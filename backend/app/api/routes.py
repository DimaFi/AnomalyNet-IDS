from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Generator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.contracts.schemas import (
    AppSettings, DebugStats, HealthResponse, ModelPresetsRegistry, ModelsRegistry,
    NormalizedFlowEvent, SettingsUpdate, StreamSnapshot,
)
from app.dependencies import get_pipeline_service
from app.pipeline.service import PipelineService
from app.preprocess.contracts import DEFAULT_CONTRACT_VERSION


router = APIRouter(prefix="/api")

def _read_version_from_git() -> str:
    try:
        import subprocess
        from pathlib import Path
        cwd = Path(__file__).parent.parent.parent.parent
        r = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(cwd), capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().lstrip("v")   # "v2.2.3" → "2.2.3"
        r2 = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(cwd), capture_output=True, text=True, timeout=5,
        )
        return r2.stdout.strip() if r2.returncode == 0 else "dev"
    except Exception:
        return "dev"


# Computed once at import time (when the server starts).
# The frontend prepends its own "v", so we return the bare number.
_APP_VERSION: str = _read_version_from_git()


def _get_app_version() -> str:
    return _APP_VERSION


@router.get("/health", response_model=HealthResponse)
def get_health(service: PipelineService = Depends(get_pipeline_service)) -> HealthResponse:
    return HealthResponse(
        service="traffic-analysis-local-api",
        status=service.status,
        mode=service.settings.run_mode,
        active_model_id=service.settings.active_model_id,
        retention_days=service.settings.retention_days,
        contract_version=DEFAULT_CONTRACT_VERSION,
        version=_get_app_version(),
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


@router.get("/dashboard/timeseries")
def get_dashboard_timeseries(
    window: int = Query(default=60, description="Window in minutes (15, 60, or 1440)"),
    service: PipelineService = Depends(get_pipeline_service),
):
    """Aggregate recent events into per-minute buckets for time-series charts.

    Uses in-memory _recent_items (last 500 events) — no disk reads, fast.
    Returns: buckets with normal/warning/anomaly counts + TLS/DNS breakdown.
    """
    from math import floor
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff = now_ts - window * 60
    bucket_sec = 60  # 1-minute buckets

    # bucket_ts → {"normal": int, "warning": int, "anomaly": int}
    buckets: dict[int, dict[str, int]] = {}

    for ev in service._recent_items:
        try:
            ts_str = ev.event.timestamp
            if hasattr(ts_str, "timestamp"):
                ts = ts_str.timestamp()
            else:
                ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")).timestamp()
            if ts < cutoff:
                continue
            bucket = int(floor(ts / bucket_sec) * bucket_sec)
            if bucket not in buckets:
                buckets[bucket] = {"normal": 0, "warning": 0, "anomaly": 0}
            label = ev.inference.label
            buckets[bucket][label] = buckets[bucket].get(label, 0) + 1
        except Exception:
            continue

    # Fill missing buckets with zeros so frontend gets a continuous series
    sorted_keys = sorted(buckets.keys()) if buckets else []
    if sorted_keys:
        all_keys = range(int(floor(cutoff / bucket_sec) * bucket_sec), sorted_keys[-1] + bucket_sec, bucket_sec)
        for k in all_keys:
            if k not in buckets:
                buckets[k] = {"normal": 0, "warning": 0, "anomaly": 0}

    result = [
        {"ts": k, "normal": v["normal"], "warning": v["warning"], "anomaly": v["anomaly"]}
        for k, v in sorted(buckets.items())
    ]
    return {"buckets": result, "window_minutes": window, "bucket_minutes": 1}


@router.get("/dashboard/summary")
def get_dashboard_summary(
    service: PipelineService = Depends(get_pipeline_service),
):
    """Aggregate summary for pie/donut charts — attack class and event type distribution.

    Uses in-memory stats counters (updated in _run_loop) — always fast.
    """
    stats = service.debug_stats()
    # event type breakdown from recent items
    type_counts: dict[str, int] = {"flow": 0, "dns": 0, "tls": 0}
    for ev in service._recent_items:
        et = getattr(ev, "event_type", None) or "flow"
        type_counts[et] = type_counts.get(et, 0) + 1

    return {
        "by_class":      stats.events_by_attack_class,
        "by_verdict":    stats.events_by_label,
        "by_event_type": type_counts,
        "total_events":  stats.uptime_events_total,
        "avg_score":     stats.avg_score,
    }


@router.get("/geoip/{ip}")
def get_geoip(ip: str):
    """Offline GeoIP lookup — private ranges and major RIR blocks. No network calls."""
    from app.security.geoip import lookup
    return lookup(ip)


@router.get("/capabilities")
def get_capabilities():
    """Return platform capabilities — what features are available on the current OS.
    Frontend uses this to hide/show features (blocking, autostart, capture status).
    """
    from app.platform import get_capabilities as _get_caps
    return _get_caps().to_dict()


@router.get("/debug/registry")
def get_registry_state(service: PipelineService = Depends(get_pipeline_service)):
    """Returns the current state of the plugin registry — which pipelines/preprocessors/models
    are actually registered. Used to diagnose pipeline loading issues."""
    from app.plugins.registry import get_registry
    registry = get_registry()
    s = service.settings
    return {
        "models_dir": s.models_dir,
        "models_dir_exists": __import__("pathlib").Path(s.models_dir).exists() if s.models_dir else False,
        "active_model_id": s.active_model_id,
        "pipelines": sorted(registry.pipelines.keys()),
        "preprocessors": sorted(registry.preprocessors.keys()),
        "models": sorted(registry.models.keys()),
        "pipeline_errors": {
            name: cfg.validate(registry)
            for name, cfg in registry.pipelines.items()
            if cfg.validate(registry)
        },
    }


_PRIORITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "info": 1}
_SEVERITY_MAP    = {"critical": 1, "high": 2, "medium": 3, "info": 4}


def _iter_history(
    service: PipelineService,
    from_ts: float,
    to_ts: float,
    min_priority: str,
) -> Generator[dict[str, Any], None, None]:
    """Yield raw event dicts from NDJSON history files within the time window."""
    min_weight = _PRIORITY_WEIGHT.get(min_priority, 0)
    history_dir = service.history_dir
    for path in sorted(history_dir.glob("*.ndjson")):
        # Quick skip: file date outside range
        try:
            file_date = datetime.fromisoformat(path.stem).date()
            file_ts = datetime.combine(file_date, datetime.min.time(), tzinfo=timezone.utc).timestamp()
            if file_ts > to_ts + 86400:
                continue
            if file_ts + 86400 < from_ts:
                continue
        except ValueError:
            pass
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = ev.get("event", {}).get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                except (ValueError, AttributeError):
                    continue
                if ts < from_ts or ts > to_ts:
                    continue
                prio = ev.get("priority", "info")
                if min_weight > 0 and _PRIORITY_WEIGHT.get(prio, 1) < min_weight:
                    continue
                yield ev


def _eve_line(ev: dict[str, Any]) -> str:
    event      = ev.get("event", {})
    inf        = ev.get("inference", {})
    prio       = ev.get("priority", "info")
    mitre      = ev.get("mitre") or {}
    ev_type    = ev.get("event_type", "flow")
    metadata   = ev.get("metadata") or {}
    ts_raw  = event.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).strftime("%Y-%m-%dT%H:%M:%S.%f+0000")
    except (ValueError, AttributeError):
        ts = ts_raw

    if ev_type == "dns":
        obj: dict[str, Any] = {
            "timestamp":  ts,
            "event_type": "dns",
            "src_ip":     event.get("src_ip", ""),
            "proto":      "DNS",
            "alert": {
                "action":       "allowed",
                "severity":     _SEVERITY_MAP.get(prio, 4),
                "signature":    "AnomalyNet DNS Detection",
                "signature_id": 9000002,
                "category":     inf.get("attack_class") or "dns_anomaly",
                "rev":          1,
            },
            "dns": {
                "domain":   metadata.get("domain", ""),
                "type":     metadata.get("dns_alert_type", ""),
                "entropy":  metadata.get("entropy"),
            },
            "anomalynet": {
                "score":        inf.get("score", 0.0),
                "verdict":      inf.get("label", ""),
                "attack_class": inf.get("attack_class"),
                "priority":     prio,
                "model_id":     inf.get("model_id", ""),
                "mitre_id":     mitre.get("id"),
                "mitre_tactic": mitre.get("tactic"),
            },
        }
    else:
        obj = {
            "timestamp":  ts,
            "event_type": "alert",
            "src_ip":     event.get("src_ip", ""),
            "src_port":   event.get("src_port", 0),
            "dest_ip":    event.get("dst_ip", ""),
            "dest_port":  event.get("dst_port", 0),
            "proto":      event.get("protocol", "TCP"),
            "alert": {
                "action":       "allowed",
                "severity":     _SEVERITY_MAP.get(prio, 4),
                "signature":    "AnomalyNet ML Detection",
                "signature_id": 9000001,
                "category":     inf.get("attack_class") or "unknown",
                "rev":          1,
            },
            "flow": {
                "pkts_toserver":  event.get("packet_count", 0),
                "pkts_toclient":  0,
                "bytes_toserver": event.get("byte_count", 0),
                "bytes_toclient": 0,
            },
            "anomalynet": {
                "score":        inf.get("score", 0.0),
                "verdict":      inf.get("label", ""),
                "attack_class": inf.get("attack_class"),
                "priority":     prio,
                "model_id":     inf.get("model_id", ""),
                "mitre_id":     mitre.get("id"),
                "mitre_tactic": mitre.get("tactic"),
            },
        }
    return json.dumps(obj, ensure_ascii=False)


@router.get("/export/eve")
def export_eve(
    from_ts: float = Query(default=None),
    to_ts:   float = Query(default=None),
    min_priority: str = Query(default="all"),
    service: PipelineService = Depends(get_pipeline_service),
):
    now = datetime.now(timezone.utc).timestamp()
    _from = from_ts if from_ts is not None else now - 86400
    _to   = to_ts   if to_ts   is not None else now

    def generate():
        for ev in _iter_history(service, _from, _to, min_priority):
            yield _eve_line(ev) + "\n"

    filename = f"anomalynet-eve-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/csv")
def export_csv(
    from_ts: float = Query(default=None),
    to_ts:   float = Query(default=None),
    min_priority: str = Query(default="all"),
    service: PipelineService = Depends(get_pipeline_service),
):
    now = datetime.now(timezone.utc).timestamp()
    _from = from_ts if from_ts is not None else now - 86400
    _to   = to_ts   if to_ts   is not None else now

    CSV_HEADERS = [
        "timestamp", "event_type", "src_ip", "src_port", "dest_ip", "dest_port",
        "proto", "verdict", "attack_class", "score", "priority",
        "mitre_id", "mitre_tactic", "domain", "action",
    ]

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(CSV_HEADERS)
        yield buf.getvalue()
        for ev in _iter_history(service, _from, _to, min_priority):
            event    = ev.get("event", {})
            inf      = ev.get("inference", {})
            mitre    = ev.get("mitre") or {}
            prio     = ev.get("priority", "info")
            ev_type  = ev.get("event_type", "flow")
            metadata = ev.get("metadata") or {}
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                event.get("timestamp", ""),
                ev_type,
                event.get("src_ip", ""),
                event.get("src_port", "") if ev_type == "flow" else "",
                event.get("dst_ip", "") if ev_type == "flow" else "",
                event.get("dst_port", "") if ev_type == "flow" else "",
                event.get("protocol", ""),
                inf.get("label", ""),
                inf.get("attack_class") or "",
                inf.get("score", ""),
                prio,
                mitre.get("id") or "",
                mitre.get("tactic") or "",
                metadata.get("domain", ""),
                "allowed",
            ])
            yield buf.getvalue()

    filename = f"anomalynet-events-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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

