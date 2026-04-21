"""
REST API для системы плагинов AnomalyNet.

Endpoints:
  GET  /api/plugins/preprocessors          — список зарегистрированных препроцессоров
  GET  /api/plugins/models                 — список зарегистрированных моделей
  GET  /api/plugins/pipelines              — список pipeline конфигов
  POST /api/plugins/pipelines              — создать пользовательский pipeline
  DELETE /api/plugins/pipelines/{name}     — удалить пользовательский pipeline
  POST /api/plugins/reload                 — перезагрузить плагины из папки plugins/
  POST /api/plugins/pipelines/{name}/validate — проверить pipeline на корректность
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.plugins.registry import get_registry
from app.plugins.pipeline_config import PipelineConfig

plugins_router = APIRouter(prefix="/api/plugins", tags=["plugins"])


# ── Ответные модели ───────────────────────────────────────────────────────────

class ReloadResponse(BaseModel):
    discovered: int
    message: str


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[str]


# ── Препроцессоры ─────────────────────────────────────────────────────────────

@plugins_router.get("/preprocessors")
def list_preprocessors() -> list[dict]:
    """Возвращает метаданные всех зарегистрированных препроцессоров."""
    registry = get_registry()
    return [p.get_metadata() for p in registry.preprocessors.values()]


# ── Модели ────────────────────────────────────────────────────────────────────

@plugins_router.get("/models")
def list_models() -> list[dict]:
    """Возвращает метаданные всех зарегистрированных моделей."""
    registry = get_registry()
    return [m.get_metadata() for m in registry.models.values()]


# ── Pipeline конфиги ──────────────────────────────────────────────────────────

@plugins_router.get("/pipelines")
def list_pipelines() -> list[dict]:
    """Возвращает все зарегистрированные pipeline конфиги (builtin + пользовательские)."""
    registry = get_registry()
    return [cfg.to_dict() for cfg in registry.pipelines.values()]


@plugins_router.post("/pipelines", status_code=201)
def create_pipeline(data: dict) -> dict:
    """
    Создаёт пользовательский pipeline из JSON-тела.

    Тело запроса — PipelineConfig.to_dict() формат:
    {
      "name": "my_pipeline",
      "description": "...",
      "entry_stage": "stage1",
      "stages": {
        "stage1": { "preprocessor_name": "cicflowmeter_71", "model_name": "...", ... }
      }
    }
    Builtin пайплайны (is_builtin=true) перезаписать нельзя.
    """
    registry = get_registry()

    try:
        cfg = PipelineConfig.from_dict(data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Неверный формат pipeline: {exc}")

    # Запрещаем перезапись builtin через API
    existing = registry.pipelines.get(cfg.name)
    if existing and existing.is_builtin:
        raise HTTPException(
            status_code=403,
            detail=f"Pipeline '{cfg.name}' является встроенным и не может быть перезаписан",
        )

    cfg = PipelineConfig(
        name=cfg.name,
        description=cfg.description,
        entry_stage=cfg.entry_stage,
        stages=cfg.stages,
        is_builtin=False,   # пользовательские всегда is_builtin=False
    )

    errors = cfg.validate(registry)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Pipeline не прошёл валидацию", "errors": errors},
        )

    registry.register_pipeline(cfg)
    registry.save_user_pipelines()
    return cfg.to_dict()


@plugins_router.delete("/pipelines/{name}", status_code=200)
def delete_pipeline(name: str) -> dict:
    """Удаляет пользовательский pipeline. Builtin пайплайны удалить нельзя."""
    registry = get_registry()
    try:
        deleted = registry.delete_pipeline(name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' не найден")
    return {"deleted": name}


@plugins_router.post("/pipelines/{name}/validate")
def validate_pipeline(name: str) -> ValidateResponse:
    """Проверяет pipeline на корректность относительно текущего реестра."""
    registry = get_registry()
    cfg = registry.pipelines.get(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' не найден")
    errors = cfg.validate(registry)
    return ValidateResponse(valid=len(errors) == 0, errors=errors)


# ── Перезагрузка ──────────────────────────────────────────────────────────────

@plugins_router.post("/reload")
def reload_plugins() -> ReloadResponse:
    """
    Сканирует папку plugins/ и загружает новые плагины.
    Уже зарегистрированные плагины с тем же именем перезаписываются.
    """
    registry = get_registry()
    count = registry.discover_plugins()
    return ReloadResponse(
        discovered=count,
        message=f"Загружено {count} плагинов из папки plugins/",
    )
