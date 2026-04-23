from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.contracts.schemas import AppSettings, ModelPresetsRegistry, ModelsRegistry, PipelineEvent


class JsonFileStore:
    def __init__(self, app_root: Path) -> None:
        self._config_dir = app_root / "config"
        self._history_dir = app_root / "data" / "history"
        self._settings_path = self._config_dir / "settings.json"
        self._models_path = self._config_dir / "models_registry.json"
        self._presets_path = self._config_dir / "model_presets.json"
        # Root for resolving relative model paths (env override → app_root / models)
        self._models_root = Path(
            os.environ.get("ANOMALYNET_MODELS_ROOT", str(app_root / "models"))
        )

    def load_settings(self) -> AppSettings:
        if not self._settings_path.exists():
            default = AppSettings()
            self.save_settings(default)
            return default
        return AppSettings.model_validate(self._read_json(self._settings_path))

    def save_settings(self, settings: AppSettings) -> AppSettings:
        self._write_json(self._settings_path, settings.model_dump(mode="json"))
        return settings

    def load_presets(self) -> ModelPresetsRegistry:
        """Load model presets, filling empty paths from ANOMALYNET_MODELS_ROOT."""
        raw = self._read_json(self._presets_path)
        # Fill model paths from environment if not set in preset
        stage1_dir   = str(self._models_root / "stage1")
        stage1_art   = str(self._models_root / "stage1_artifacts")
        stage2_dir   = str(self._models_root / "stage2")
        stage3_dir   = str(self._models_root / "stage3")
        stage3_art   = str(self._models_root / "stage3_artifacts")

        for preset in raw.get("presets", []):
            pid = preset.get("id")
            if pid in ("binary-v1", "simple-cascade", "advanced-cascade", "cascade-routed"):
                if not preset.get("catboost_model_dir"):
                    preset["catboost_model_dir"] = stage1_dir
                if not preset.get("preprocessing_artifacts_dir"):
                    preset["preprocessing_artifacts_dir"] = stage1_art
            if pid == "simple-cascade":
                if not preset.get("catboost_secondary_model_dir"):
                    preset["catboost_secondary_model_dir"] = stage2_dir
            if pid in ("advanced-cascade", "cascade-routed"):
                if not preset.get("catboost_secondary_model_dir"):
                    preset["catboost_secondary_model_dir"] = stage3_dir
                if not preset.get("catboost_secondary_artifacts_dir"):
                    preset["catboost_secondary_artifacts_dir"] = stage3_art
            if pid == "cascade-routed":
                if not preset.get("catboost_stage3_model_dir"):
                    preset["catboost_stage3_model_dir"] = stage3_dir
                if not preset.get("catboost_stage3_artifacts_dir"):
                    preset["catboost_stage3_artifacts_dir"] = stage3_art

        return ModelPresetsRegistry.model_validate(raw)

    def load_models(self) -> ModelsRegistry:
        return ModelsRegistry.model_validate(self._read_json(self._models_path))

    def save_models(self, registry: ModelsRegistry) -> ModelsRegistry:
        self._write_json(self._models_path, registry.model_dump(mode="json"))
        return registry

    def append_history(self, item: PipelineEvent) -> None:
        self._history_dir.mkdir(parents=True, exist_ok=True)
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
