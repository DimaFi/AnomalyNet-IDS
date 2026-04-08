from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from uuid import uuid4

from app.capture.factory import build_capture_adapter
from app.contracts.schemas import (
    AlertRecord, AppSettings, ModelDescriptor, ModelsRegistry,
    PipelineEvent, StatusLevel, StreamSnapshot,
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
        # Persistent capture adapter (long-lived for real capture modes)
        self._capture_adapter = None
        self._capture_mode: str = ""

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

    async def shutdown(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            finally:
                self._loop_task = None
        await self._stop_adapter()

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
        """Returns existing adapter or creates a new one if mode changed."""
        current_mode = self._settings.run_mode
        if self._capture_mode != current_mode:
            await self._stop_adapter()
            self._capture_adapter = build_capture_adapter(current_mode, self._settings)
            start = getattr(self._capture_adapter, "start", None)
            if start:
                await start()
            self._capture_mode = current_mode
        return self._capture_adapter

    async def _run_loop(self) -> None:
        self._status = "active"
        while True:
            if not self._settings.capture_enabled:
                self._status = "idle"
                await asyncio.sleep(1.0)
                continue

            descriptor = self._active_descriptor()
            preprocess = build_preprocessing_pipeline(descriptor, self._settings)
            model = build_model_adapter(descriptor, self._settings)

            try:
                adapter = await self._get_or_rebuild_adapter()
                event = await adapter.next_event()
                features = preprocess.transform(event)
                inference = model.infer(features)

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
                    if self._settings.auto_block and inference.label == "anomaly":
                        await self._try_block_ip(event.src_ip)

                pipeline_event = PipelineEvent(
                    event=event, features=features, inference=inference, alert=alert
                )
                self._recent_items.appendleft(pipeline_event)
                self._store.append_history(pipeline_event)
                self._store.apply_retention(self._settings.retention_days)
                await self._fan_out(pipeline_event)
                self._status = "active"

            except asyncio.CancelledError:
                raise
            except Exception:
                self._status = "warning"
                await asyncio.sleep(2.0)

    async def _try_block_ip(self, ip: str) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-I", "INPUT", "-s", ip, "-j", "DROP",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception:
            pass

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
        return self._models

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
            _, stderr = await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False
        except Exception:
            return False
