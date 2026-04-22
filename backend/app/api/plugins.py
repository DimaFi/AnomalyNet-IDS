"""
REST API для системы плагинов AnomalyNet.

Endpoints:
  GET    /api/plugins/preprocessors            — список зарегистрированных препроцессоров
  GET    /api/plugins/models                   — список зарегистрированных моделей
  GET    /api/plugins/pipelines                — список pipeline конфигов
  POST   /api/plugins/pipelines                — создать пользовательский pipeline
  DELETE /api/plugins/pipelines/{name}         — удалить пользовательский pipeline
  POST   /api/plugins/reload                   — перезагрузить плагины из папки plugins/
  POST   /api/plugins/pipelines/{name}/validate — проверить pipeline на корректность
  POST   /api/plugins/upload                   — загрузить .py файл в папку plugins/
  GET    /api/plugins/files                    — список файлов в папке plugins/
  DELETE /api/plugins/files/{filename}         — удалить файл из plugins/
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
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


@plugins_router.post("/pipelines/{name}/test")
def test_pipeline(name: str, ignore_gates: bool = False) -> dict:
    """
    Запускает pipeline с синтетическим тестовым событием.

    Создаёт NormalizedFlowEvent с нулевыми значениями признаков (raw_features = {feat: 0.0}),
    прогоняет через все стадии pipeline и возвращает пошаговую трассировку.

    ignore_gates=true — пропускает gate-условия и принудительно запускает все стадии каскада.
    Полезно для каскадных pipeline где Stage1-gate обычно возвращает "normal" на нулевых данных.
    """
    import uuid
    from datetime import datetime, timezone
    from app.contracts.schemas import NormalizedFlowEvent

    registry = get_registry()
    cfg = registry.pipelines.get(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' не найден")

    # Собираем имена признаков из первого препроцессора для заполнения raw_features
    entry_stage_cfg = cfg.stages.get(cfg.entry_stage)
    raw_features: dict[str, float] = {}
    if entry_stage_cfg:
        prep = registry.preprocessors.get(entry_stage_cfg.preprocessor_name)
        if prep:
            names = prep.get_feature_names()
            raw_features = {n: 0.0 for n in names} if names else {"_dummy": 0.0}

    # Создаём синтетическое событие
    event = NormalizedFlowEvent(
        event_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        source="plugin_test",
        direction="inbound",
        protocol="TCP",
        src_ip="192.168.1.100",
        dst_ip="10.0.0.1",
        src_port=12345,
        dst_port=80,
        packet_count=10,
        byte_count=1500,
        duration_ms=100,
        risk_hint=0.0,
        raw_features=raw_features if raw_features else None,
        raw_features_cic2023={},
    )

    trace = []
    current_stage_name: str | None = cfg.entry_stage
    final_verdict = None
    final_score = None

    while current_stage_name:
        stage = cfg.stages[current_stage_name]
        stage_result: dict = {
            "stage":        current_stage_name,
            "preprocessor": stage.preprocessor_name,
            "model":        stage.model_name,
            "is_gate":      stage.is_gate,
        }

        preprocessor = registry.preprocessors.get(stage.preprocessor_name)
        model        = registry.models.get(stage.model_name)

        if preprocessor is None:
            stage_result["ok"]    = False
            stage_result["error"] = f"Препроцессор '{stage.preprocessor_name}' не зарегистрирован. Проверьте пути к артефактам в Настройках."
            trace.append(stage_result)
            break
        if model is None:
            stage_result["ok"]    = False
            stage_result["error"] = f"Модель '{stage.model_name}' не зарегистрирована. Проверьте пути к моделям в Настройках."
            trace.append(stage_result)
            break

        try:
            fv      = preprocessor.transform(event)
            verdict = model.predict(fv)

            stage_result["ok"]           = True
            stage_result["feature_count"] = len(fv.features)
            stage_result["schema_id"]    = fv.schema_id
            stage_result["verdict"]      = verdict.verdict
            stage_result["score"]        = round(verdict.score, 4)
            stage_result["attack_class"] = verdict.attack_class
            stage_result["reason"]       = verdict.reason
            final_verdict = verdict.verdict
            final_score   = round(verdict.score, 4)
        except Exception as exc:
            stage_result["ok"]    = False
            stage_result["error"] = str(exc)
            trace.append(stage_result)
            break

        trace.append(stage_result)

        gate_blocked = stage.is_gate and verdict.verdict == "normal" and not ignore_gates
        if gate_blocked:
            stage_result["gate_blocked"] = True
            trace.append(stage_result)
            break
        current_stage_name = stage.next_stage

    all_ok = bool(trace) and all(s.get("ok", False) for s in trace)
    gate_was_skipped = ignore_gates and any(s.get("is_gate") for s in trace)
    return {
        "pipeline":         name,
        "ok":               all_ok,
        "stages_run":       len(trace),
        "trace":            trace,
        "final_verdict":    final_verdict,
        "final_score":      final_score,
        "ignore_gates":     ignore_gates,
        "note": (
            "Все gate-условия пропущены — проверяется только что каждая стадия может выполниться. "
            "Вердикт не отражает реальную детекцию."
            if gate_was_skipped else
            "Тест использует нулевые значения признаков — вердикт не отражает реальную детекцию, "
            "но подтверждает что pipeline корректно зарегистрирован и данные проходят через все стадии."
        ),
    }


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


# ── Файловые операции ─────────────────────────────────────────────────────────

_PLUGINS_FOLDER = Path(__file__).parent.parent.parent.parent / "plugins"


@plugins_router.get("/files")
def list_plugin_files() -> list[dict]:
    """Возвращает список .py файлов в папке plugins/ (пользовательские плагины)."""
    if not _PLUGINS_FOLDER.exists():
        return []
    files = []
    for f in sorted(_PLUGINS_FOLDER.glob("*.py")):
        if f.name.startswith("_"):
            continue
        files.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "is_example": f.name.startswith("example_"),
        })
    return files


@plugins_router.post("/upload", status_code=201)
async def upload_plugin_file(file: UploadFile = File(...)) -> dict:
    """
    Загружает .py файл в папку plugins/ и автоматически перезагружает плагины.

    Принимает multipart/form-data с полем 'file'.
    Имя файла сохраняется как есть (без пути). Разрешены только .py файлы.
    После загрузки автоматически вызывает discover_plugins().
    """
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=422, detail="Разрешены только .py файлы")

    # Безопасное имя файла — только basename, без пути
    safe_name = Path(file.filename).name
    if safe_name.startswith("_"):
        raise HTTPException(status_code=422, detail="Имя файла не должно начинаться с '_'")

    _PLUGINS_FOLDER.mkdir(parents=True, exist_ok=True)
    dest = _PLUGINS_FOLDER / safe_name

    content = await file.read()
    dest.write_bytes(content)

    # Автоматически перезагрузить плагины после загрузки
    registry = get_registry()
    discovered = registry.discover_plugins()

    return {
        "filename": safe_name,
        "size_bytes": len(content),
        "discovered": discovered,
        "message": f"Файл '{safe_name}' загружен, обнаружено плагинов: {discovered}",
    }


@plugins_router.delete("/files/{filename}", status_code=200)
def delete_plugin_file(filename: str) -> dict:
    """Удаляет .py файл из папки plugins/."""
    safe_name = Path(filename).name
    if not safe_name.endswith(".py"):
        raise HTTPException(status_code=422, detail="Разрешены только .py файлы")

    target = _PLUGINS_FOLDER / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Файл '{safe_name}' не найден")

    target.unlink()
    return {"deleted": safe_name}
