from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from uuid import uuid4

logger = logging.getLogger(__name__)

from app.capture.factory import build_capture_adapter
from app.contracts.schemas import (
    AlertRecord, AppSettings, DebugStats, ModelDescriptor, ModelPreset, ModelPresetsRegistry,
    ModelsRegistry, PipelineEvent, StatusLevel, StreamSnapshot,
)
from app.model.factory import build_model_adapter
from app.preprocess.factory import build_preprocessing_pipeline
from app.storage.json_store import JsonFileStore


class PipelineService:
    def __init__(self, store: JsonFileStore) -> None:
        self._store = store
        self._settings = store.load_settings()
        self._models = store.load_models()
        self._status: StatusLevel = "idle"
        self._recent_items: deque[PipelineEvent] = deque(maxlen=500)
        self._subscribers: set[asyncio.Queue[PipelineEvent]] = set()
        self._loop_task: asyncio.Task[None] | None = None
        self._unblock_task: asyncio.Task[None] | None = None
        # Persistent capture adapter (long-lived for real capture modes)
        self._capture_adapter = None
        self._capture_mode: str = ""   # tracks run_mode + detection_mode
        # Cached pipeline + model — rebuilt only when active_model_id or settings change
        self._preprocess_cache = None
        self._model_cache = None
        self._cache_key: tuple | None = None  # (active_model_id, relevant settings hash)
        # Blocked IPs registry — tracks IPs blocked via iptables by this service
        self._blocked_ips_registry: dict[str, str] = {}  # ip → ISO timestamp
        # DeviceTracker hook (optional — set from main.py lifespan)
        self._device_tracker = None
        # Rolling counters for debug stats (reset on restart)
        self._total_events: int = 0
        self._label_counts: dict[str, int] = {"normal": 0, "warning": 0, "anomaly": 0}
        self._proto_counts: dict[str, int] = {}
        self._class_counts: dict[str, int] = {}
        self._src_ip_counts: dict[str, int] = {}
        self._dst_port_counts: dict[str, int] = {}
        self._scores: list[float] = []  # last 500 scores
        self._last_retention_check: float = 0.0  # monotonic time of last retention run

    @property
    def settings(self) -> AppSettings:
        return self._settings

    @property
    def models(self) -> ModelsRegistry:
        return self._models

    @property
    def status(self) -> StatusLevel:
        return self._status

    def _active_descriptor(self) -> ModelDescriptor:
        active_id = self._settings.active_model_id
        for item in self._models.items:
            if item.model_id == active_id:
                return item
        if not self._models.items:
            raise RuntimeError("Реестр моделей пуст — проверьте config/models_registry.json")
        return self._models.items[0]

    async def start(self) -> None:
        if self._settings.stream_autostart and self._loop_task is None:
            self._loop_task = asyncio.create_task(self._run_loop())
        self._unblock_task = asyncio.create_task(self._auto_unblock_loop())

    async def shutdown(self) -> None:
        for task in (self._loop_task, self._unblock_task):
            if task:
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
        self._loop_task = None
        self._unblock_task = None
        try:
            await asyncio.wait_for(self._stop_adapter(), timeout=5.0)
        except asyncio.TimeoutError:
            pass

    async def _stop_adapter(self) -> None:
        if self._capture_adapter is not None:
            stop = getattr(self._capture_adapter, "stop", None)
            if stop:
                try:
                    await stop()
                except Exception:
                    pass
            self._capture_adapter = None
            self._capture_mode = ""

    async def _get_or_rebuild_adapter(self):
        """Returns existing adapter or creates a new one if run_mode or detection_mode changed."""
        current_mode = f"{self._settings.run_mode}:{self._settings.detection_mode}"
        if self._capture_mode != current_mode:
            await self._stop_adapter()
            adapter = build_capture_adapter(self._settings.run_mode, self._settings)
            start = getattr(adapter, "start", None)
            if start:
                await start()
            # Only update state after successful start
            self._capture_adapter = adapter
            self._capture_mode = current_mode
        return self._capture_adapter

    def _make_cache_key(self) -> tuple:
        s = self._settings
        return (
            s.active_model_id,
            s.run_mode,
            s.detection_mode,
            s.catboost_model_dir,
            s.preprocessing_artifacts_dir,
            s.catboost_secondary_model_dir,
            s.catboost_secondary_artifacts_dir,
            s.catboost_threshold,
        )

    def _get_pipeline_and_model(self):
        key = self._make_cache_key()
        if key != self._cache_key:
            active_id = self._settings.active_model_id
            if active_id.startswith("plugin:"):
                pipeline_name = active_id[len("plugin:"):]
                from app.plugins.runner import PluginPipelineRunner
                runner = PluginPipelineRunner(pipeline_name)
                self._preprocess_cache = runner
                self._model_cache = runner
            else:
                descriptor = self._active_descriptor()
                self._preprocess_cache = build_preprocessing_pipeline(descriptor, self._settings)
                self._model_cache = build_model_adapter(descriptor, self._settings)
            self._cache_key = key
        return self._preprocess_cache, self._model_cache

    async def _run_loop(self) -> None:
        """Main pipeline loop — drains queue in mini-batches for higher throughput.
        CatBoost batch inference is 5-10x faster than one-by-one calls."""
        self._status = "active"
        BATCH_SIZE = 16  # collect up to 16 events per iteration before inference

        while True:
            if not self._settings.capture_enabled:
                self._status = "idle"
                await asyncio.sleep(1.0)
                continue

            try:
                preprocess, model = self._get_pipeline_and_model()
                adapter = await self._get_or_rebuild_adapter()

                # Wait for at least one event, then drain up to BATCH_SIZE - 1 more
                events = [await adapter.next_event()]
                while len(events) < BATCH_SIZE:
                    try:
                        events.append(adapter._queue.get_nowait())
                    except Exception:
                        break

                is_auto = self._settings.active_model_id == "plugin:auto"

                for event in events:
                    try:
                        if is_auto:
                            pipeline_name = self._resolve_auto_pipeline(event.src_ip)
                            from app.plugins.runner import PluginPipelineRunner
                            runner = PluginPipelineRunner(pipeline_name)
                            features = runner.transform(event)
                            inference = runner.infer(features)
                        else:
                            features = preprocess.transform(event)
                            inference = model.infer(features)
                            pipeline_name = None
                    except Exception as exc:
                        logger.warning("Pipeline failed for event %s: %s", event.event_id, exc)
                        continue

                    # Enrich with device info
                    ev_device_type: str | None = None
                    ev_device_name: str | None = None
                    if self._device_tracker is not None:
                        try:
                            dev = self._device_tracker.get_device_by_ip(event.src_ip)
                            if dev is not None:
                                ev_device_type = dev.device_type
                                ev_device_name = dev.display_name()
                        except Exception:
                            pass

                    alert = None
                    if inference.label != "normal":
                        alert = AlertRecord(
                            alert_id=str(uuid4()),
                            timestamp=datetime.now(timezone.utc),
                            level=inference.label,
                            title=f"Обнаружена атака от {event.src_ip}",
                            details=inference.reason,
                            event_id=event.event_id,
                        )
                        whitelist = self._settings.whitelist_ips or []
                        if self._settings.auto_block and event.src_ip not in whitelist:
                            level = self._settings.auto_block_level or "anomaly"
                            should_block = (
                                inference.label == "anomaly" or
                                (level == "warning" and inference.label == "warning")
                            )
                            if should_block:
                                await self._try_block_ip(event.src_ip)

                    self._total_events += 1
                    self._label_counts[inference.label] = self._label_counts.get(inference.label, 0) + 1
                    self._proto_counts[event.protocol] = self._proto_counts.get(event.protocol, 0) + 1
                    if inference.attack_class:
                        self._class_counts[inference.attack_class] = self._class_counts.get(inference.attack_class, 0) + 1
                    self._src_ip_counts[event.src_ip] = self._src_ip_counts.get(event.src_ip, 0) + 1
                    self._dst_port_counts[str(event.dst_port)] = self._dst_port_counts.get(str(event.dst_port), 0) + 1
                    self._scores.append(inference.score)
                    if len(self._scores) > 500:
                        self._scores = self._scores[-500:]

                    pipeline_event = PipelineEvent(
                        event=event, features=features, inference=inference, alert=alert,
                        device_type=ev_device_type,
                        device_name=ev_device_name,
                        pipeline_used=pipeline_name if is_auto else None,
                    )
                    self._recent_items.appendleft(pipeline_event)
                    self._store.append_history(pipeline_event)
                    await self._fan_out(pipeline_event)

                    if self._device_tracker is not None:
                        try:
                            self._device_tracker.on_flow_event(event, inference)
                        except Exception:
                            pass

                # Apply retention at most once per hour to avoid frequent filesystem ops
                now = time.monotonic()
                if now - self._last_retention_check > 3600:
                    self._store.apply_retention(self._settings.retention_days)
                    self._last_retention_check = now
                self._status = "active"

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Pipeline loop error: %s", exc, exc_info=True)
                self._status = "warning"
                await asyncio.sleep(2.0)

    async def _try_block_ip(self, ip: str) -> None:
        if ip in self._blocked_ips_registry:
            return  # already blocked, skip duplicate iptables call
        try:
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-I", "INPUT", "-s", ip, "-j", "DROP",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if proc.returncode == 0:
                self._blocked_ips_registry[ip] = datetime.now(timezone.utc).isoformat()
        except Exception:
            pass

    async def _auto_unblock_loop(self) -> None:
        """Background task: automatically unblock IPs after the configured cooldown."""
        while True:
            await asyncio.sleep(60)  # check every minute
            if not self._settings.auto_unblock or not self._blocked_ips_registry:
                continue
            cooldown = timedelta(minutes=self._settings.auto_unblock_cooldown_min)
            now = datetime.now(timezone.utc)
            to_unblock = [
                ip for ip, ts_str in list(self._blocked_ips_registry.items())
                if (now - datetime.fromisoformat(ts_str)) >= cooldown
            ]
            for ip in to_unblock:
                await self.unblock_ip(ip)

    async def _fan_out(self, pipeline_event: PipelineEvent) -> None:
        stale: list[asyncio.Queue[PipelineEvent]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(pipeline_event)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self._subscribers.discard(queue)

    def snapshot(self) -> StreamSnapshot:
        return StreamSnapshot(
            status=self._status,
            queue_size=len(self._recent_items),
            items=list(self._recent_items),
        )

    def history(self, limit: int = 50, offset: int = 0) -> list[PipelineEvent]:
        items = list(self._recent_items)
        if offset:
            items = items[offset:]
        return items[:limit] if limit > 0 else items

    def update_settings(self, updated: AppSettings) -> AppSettings:
        self._settings = self._store.save_settings(updated)
        self._cache_key = None  # Force pipeline/model rebuild on next event
        self._store.apply_retention(self._settings.retention_days)
        if self._settings.stream_autostart and self._loop_task is None:
            self._loop_task = asyncio.create_task(self._run_loop())
        if not self._settings.stream_autostart and self._loop_task is not None:
            self._loop_task.cancel()
            self._loop_task = None
            self._status = "idle"
        # Rebuild plugin registry so new paths take effect immediately
        try:
            from app.plugins.builtin.presets import build_builtin_registry
            build_builtin_registry(self._settings)
        except Exception as exc:
            logger.warning("Не удалось перестроить plugin registry: %s", exc)
        return self._settings

    def select_model(self, model_id: str) -> ModelsRegistry:
        registry = self._models.model_copy(deep=True)
        registry.active_model_id = model_id
        for item in registry.items:
            item.status = "active" if item.model_id == model_id else "idle"
        self._models = self._store.save_models(registry)
        self._settings = self._store.save_settings(
            self._settings.model_copy(update={"active_model_id": model_id})
        )
        self._cache_key = None  # Force pipeline/model rebuild on next event
        return self._models

    def get_presets(self) -> ModelPresetsRegistry:
        return self._store.load_presets()

    def apply_preset(self, preset: ModelPreset) -> AppSettings:
        """Apply a model preset — updates all model-related settings at once.
        Invalidates the pipeline/model cache so changes take effect immediately."""
        update_fields: dict = {
            "active_model_id":                  preset.active_model_id,
            "run_mode":                          preset.run_mode,
            "detection_mode":                    preset.detection_mode,
            "catboost_model_dir":                preset.catboost_model_dir,
            "preprocessing_artifacts_dir":       preset.preprocessing_artifacts_dir,
            "catboost_secondary_model_dir":      preset.catboost_secondary_model_dir,
            "catboost_secondary_artifacts_dir":  preset.catboost_secondary_artifacts_dir,
            "catboost_stage3_model_dir":         preset.catboost_stage3_model_dir,
            "catboost_stage3_artifacts_dir":     preset.catboost_stage3_artifacts_dir,
        }
        # Apply general network paths only if preset explicitly sets them (non-empty)
        if preset.catboost_general_model_dir:
            update_fields["catboost_general_model_dir"] = preset.catboost_general_model_dir
        if preset.catboost_general_stage2_dir:
            update_fields["catboost_general_stage2_dir"] = preset.catboost_general_stage2_dir
        if preset.catboost_general_artifacts_dir:
            update_fields["catboost_general_artifacts_dir"] = preset.catboost_general_artifacts_dir
        updated = self._settings.model_copy(update=update_fields)
        self._settings = self._store.save_settings(updated)
        self._cache_key = None  # Force pipeline/model rebuild on next event
        # Rebuild plugin registry with new paths
        try:
            from app.plugins.builtin.presets import build_builtin_registry
            build_builtin_registry(self._settings)
        except Exception as exc:
            logger.warning("Не удалось перестроить plugin registry: %s", exc)
        # Also update active model in registry
        self.select_model(preset.active_model_id)
        return self._settings

    def debug_stats(self) -> DebugStats:
        """Returns detailed statistics for the developer debug view."""
        scores = self._scores or [0.0]
        top_ips = dict(sorted(self._src_ip_counts.items(), key=lambda x: -x[1])[:10])
        top_ports = dict(sorted(self._dst_port_counts.items(), key=lambda x: -x[1])[:10])
        ifaces = self._settings.interface_names or [self._settings.interface_name]
        return DebugStats(
            uptime_events_total=self._total_events,
            events_by_label=dict(self._label_counts),
            events_by_protocol=dict(self._proto_counts),
            events_by_attack_class=dict(self._class_counts),
            top_src_ips=top_ips,
            top_dst_ports=top_ports,
            avg_score=round(sum(scores) / len(scores), 4),
            max_score=round(max(scores), 4),
            detection_mode=self._settings.detection_mode,
            active_model_id=self._settings.active_model_id,
            interface=", ".join(ifaces),
            capture_status=self._status,
        )

    def set_device_tracker(self, tracker) -> None:
        self._device_tracker = tracker

    # ── Device-aware pipeline routing (plugin:auto mode) ──────────────────────

    _IOT_DEVICE_TYPES = frozenset({
        "iot_camera", "iot_sensor", "iot_bulb", "iot_plug",
        "router", "nas", "unknown",
    })
    _GENERAL_DEVICE_TYPES = frozenset({
        "pc_windows", "pc_linux", "pc_mac", "phone",
        "game_console", "tv", "printer",
    })

    def _resolve_auto_pipeline(self, src_ip: str) -> str:
        """Выбирает имя pipeline по типу устройства-источника.
        Возвращает 'general_network' для ПК/телефонов, иначе 'advanced'."""
        if self._device_tracker is None:
            return "advanced"
        try:
            device = self._device_tracker.get_device_by_ip(src_ip)
        except Exception:
            return "advanced"
        if device is None or device.device_type not in self._GENERAL_DEVICE_TYPES:
            return "advanced"
        from app.plugins.registry import get_registry
        if "general_network" in get_registry().pipelines:
            return "general_network"
        logger.warning("general_network pipeline не зарегистрирован, fallback → advanced для %s", src_ip)
        return "advanced"

    def subscribe(self) -> asyncio.Queue[PipelineEvent]:
        queue: asyncio.Queue[PipelineEvent] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[PipelineEvent]) -> None:
        self._subscribers.discard(queue)

    async def block_ip(self, ip: str) -> bool:
        """Manual block of an IP via iptables. Returns True on success."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-I", "INPUT", "-s", ip, "-j", "DROP",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, _ = await proc.communicate()
            if proc.returncode == 0:
                self._blocked_ips_registry[ip] = datetime.now(timezone.utc).isoformat()
            return proc.returncode == 0
        except FileNotFoundError:
            return False
        except Exception:
            return False

    async def unblock_ip(self, ip: str) -> bool:
        """Remove iptables DROP rule for an IP. Returns True on success."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-D", "INPUT", "-s", ip, "-j", "DROP",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            self._blocked_ips_registry.pop(ip, None)
            return proc.returncode == 0
        except FileNotFoundError:
            self._blocked_ips_registry.pop(ip, None)
            return False
        except Exception:
            return False

    async def unblock_all_ips(self) -> int:
        """Remove all iptables DROP rules added by this service. Returns count unblocked."""
        ips = list(self._blocked_ips_registry.keys())
        count = 0
        for ip in ips:
            success = await self.unblock_ip(ip)
            if success:
                count += 1
        return count

    def get_blocked_ips(self) -> dict[str, str]:
        """Returns dict of {ip: blocked_at_iso} for all currently tracked blocked IPs."""
        return dict(self._blocked_ips_registry)
