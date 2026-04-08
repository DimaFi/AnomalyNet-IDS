from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.contracts.schemas import AppSettings, ModelsRegistry, PipelineEvent


class JsonFileStore:
    def __init__(self, app_root: Path) -> None:
        self._config_dir = app_root / "config"
        self._history_dir = app_root / "data" / "history"
        self._settings_path = self._config_dir / "settings.json"
        self._models_path = self._config_dir / "models_registry.json"

    def load_settings(self) -> AppSettings:
        return AppSettings.model_validate(self._read_json(self._settings_path))

    def save_settings(self, settings: AppSettings) -> AppSettings:
        self._write_json(self._settings_path, settings.model_dump(mode="json"))
        return settings

    def load_models(self) -> ModelsRegistry:
        return ModelsRegistry.model_validate(self._read_json(self._models_path))

    def save_models(self, registry: ModelsRegistry) -> ModelsRegistry:
        self._write_json(self._models_path, registry.model_dump(mode="json"))
        return registry

    def append_history(self, item: PipelineEvent) -> None:
        day_path = self._history_dir / f"{datetime.now(timezone.utc).date().isoformat()}.ndjson"
        serialized = json.dumps(item.model_dump(mode="json"), ensure_ascii=False)
        with day_path.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")

    def read_recent_history(self, limit: int = 50) -> list[PipelineEvent]:
        files = sorted(self._history_dir.glob("*.ndjson"), reverse=True)
        items: list[PipelineEvent] = []
        for path in files:
            with path.open("r", encoding="utf-8") as handle:
                for line in reversed(handle.readlines()):
                    payload = json.loads(line)
                    items.append(PipelineEvent.model_validate(payload))
                    if len(items) >= limit:
                        return items
        return items

    def apply_retention(self, retention_days: int) -> None:
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=retention_days)
        for path in self._history_dir.glob("*.ndjson"):
            try:
                file_date = datetime.fromisoformat(path.stem).date()
            except ValueError:
                continue
            if file_date < cutoff:
                path.unlink(missing_ok=True)

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
