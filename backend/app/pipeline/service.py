from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone, timedelta
from uuid import uuid4

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
        self._recent_items: deque[PipelineEvent] = deque(maxlen=30)
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
        # Rolling counters for debug stats (reset on restart)
        self._total_events: int = 0
        self._label_counts: dict[str, int] = {"normal": 0, "warning": 0, "anomaly": 0}
        self._proto_counts: dict[str, int] = {}
        self._class_counts: dict[str, int] = {}
        self._src_ip_counts: dict[str, int] = {}
        self._dst_port_counts: dict[str, int] = {}
        self._scores: list[float] = []  # last 500 scores

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
            self._capture_adapter = build_capture_adapter(
                self._settings.run_mode, self._settings
            )
            start = getattr(self._capture_adapter, "start", None)
            if start:
                await start()
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

                for event in events:
                    try:
                        features = preprocess.transform(event)
                        inference = model.infer(features)
                    except Exception:
                        continue

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
                        if self._settings.auto_block and event.src_ip not in self._settings.whitelist_ips:
                            level = self._settings.auto_block_level
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
                        event=event, features=features, inference=inference, alert=alert
                    )
                    self._recent_items.appendleft(pipeline_event)
                    self._store.append_history(pipeline_event)
                    await self._fan_out(pipeline_event)

                self._store.apply_retention(self._settings.retention_days)
                self._status = "active"

            except asyncio.CancelledError:
                raise
            except Exception:
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

    def history(self, limit: int = 50) -> list[PipelineEvent]:
        return self._store.read_recent_history(limit=limit)

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
        updated = self._settings.model_copy(update={
            "active_model_id":                  preset.active_model_id,
            "run_mode":                          preset.run_mode,
            "detection_mode":                    preset.detection_mode,
            "catboost_model_dir":                preset.catboost_model_dir,
            "preprocessing_artifacts_dir":       preset.preprocessing_artifacts_dir,
            "catboost_secondary_model_dir":      preset.catboost_secondary_model_dir,
            "catboost_secondary_artifacts_dir":  preset.catboost_secondary_artifacts_dir,
        })
        self._settings = self._store.save_settings(updated)
        self._cache_key = None  # Force pipeline/model rebuild on next event
        # Also update active model in registry
        self.select_model(preset.active_model_id)
        return self._settings

    def debug_stats(self) -> DebugStats:
        """Returns detailed statistics for the developer debug view."""
        scores = self._scores or [0.0]
        top_ips = dict(sorted(self._src_ip_counts.items(), key=lambda x: -x[1])[:10])
        top_ports = dict(sorted(self._dst_port_counts.items(), key=lambda x: -x[1])[:10])
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
            interface=self._settings.interface_name,
            capture_status=self._status,
        )

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
