from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.contracts.schemas import AppSettings, ModelPresetsRegistry, ModelsRegistry, PipelineEvent
from app.core import get_user_data_dir


class JsonFileStore:
    def __init__(self, app_root: Path) -> None:
        # Read-only config (tracked in git) — presets, model registry, default settings
        self._config_dir = app_root / "config"

        # Writable user data — settings and history survive git pull / updates
        self._user_dir = get_user_data_dir()
        self._user_dir.mkdir(parents=True, exist_ok=True)
        (self._user_dir / "data" / "history").mkdir(parents=True, exist_ok=True)

        self._settings_path = self._user_dir / "settings.json"
        self._models_path = self._config_dir / "models_registry.json"
        self._presets_path = self._config_dir / "model_presets.json"
        self._history_dir = self._user_dir / "data" / "history"

    @property
    def history_dir(self) -> Path:
        return self._history_dir

        # Migrate settings from old location if user data dir is fresh
        self._migrate_settings_if_needed(app_root)

    def _migrate_settings_if_needed(self, app_root: Path) -> None:
        """
        One-time migration: if user settings don't exist yet, copy from the
        app config dir (old location). Also migrates ml_base_dir → models_dir.
        Falls back to AppSettings defaults.
        """
        if self._settings_path.exists():
            # May still need schema migration (old fields → new)
            self._migrate_schema()
            return
        old_path = app_root / "config" / "settings.json"
        if old_path.exists():
            try:
                shutil.copy2(old_path, self._settings_path)
                self._migrate_schema()
                return
            except Exception:
                pass
        # Write defaults
        self.save_settings(AppSettings())

    def _migrate_schema(self) -> None:
        """Migrate old settings fields to new schema without data loss."""
        try:
            raw = self._read_json(self._settings_path)
        except Exception:
            return

        changed = False

        # ml_base_dir → models_dir (if models/ subfolder exists)
        if "ml_base_dir" in raw and not raw.get("models_dir"):
            base = raw.pop("ml_base_dir", "")
            if base:
                candidate = Path(base) / "models"
                raw["models_dir"] = str(candidate) if candidate.exists() else ""
            changed = True
        elif "ml_base_dir" in raw:
            raw.pop("ml_base_dir", None)
            changed = True

        # Remove obsolete path fields
        obsolete = {
            "catboost_model_dir", "preprocessing_artifacts_dir",
            "catboost_secondary_model_dir", "catboost_secondary_artifacts_dir",
            "catboost_stage3_model_dir", "catboost_stage3_artifacts_dir",
            "catboost_general_model_dir", "catboost_general_stage2_dir",
            "catboost_general_artifacts_dir",
        }
        for field in obsolete:
            if field in raw:
                raw.pop(field)
                changed = True

        if changed:
            self._write_json(self._settings_path, raw)

    def load_settings(self) -> AppSettings:
        if not self._settings_path.exists():
            default = AppSettings()
            self.save_settings(default)
            return default
        try:
            data = self._read_json(self._settings_path)
            return AppSettings.model_validate(data)
        except Exception:
            # Corrupt file — reset to defaults
            default = AppSettings()
            self.save_settings(default)
            return default

    def save_settings(self, settings: AppSettings) -> AppSettings:
        self._write_json(self._settings_path, settings.model_dump(mode="json"))
        return settings

    def load_presets(self) -> ModelPresetsRegistry:
        raw = self._read_json(self._presets_path)
        return ModelPresetsRegistry.model_validate(raw)

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
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
