"""
Models Manager API

GET  /api/models-manager/list          → list of installed ModelPackage info
GET  /api/models-manager/catalog       → official model catalog
POST /api/models-manager/scan          → rescan models_dir, rebuild registry
POST /api/models-manager/add           { "folder_path": "..." }
POST /api/models-manager/download/{id} → start git clone/pull, SSE stream
GET  /api/models-manager/status/{id}   → download task status
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_pipeline_service
from app.pipeline.service import PipelineService

logger = logging.getLogger(__name__)

models_manager_router = APIRouter(prefix="/api/models-manager")

# In-memory download task registry: task_id → {"status", "lines", "error"}
_download_tasks: dict[str, dict[str, Any]] = {}


# ── Response helpers ──────────────────────────────────────────────────────────

def _package_to_dict(pkg) -> dict:
    d = pkg.to_dict()
    # Convert Path objects to strings for JSON serialisation
    d["folder_path"] = str(d["folder_path"])
    d["model_file"] = str(d["model_file"])
    d["artifacts_dir"] = str(d["artifacts_dir"])
    return d


# ── Endpoints ─────────────────────────────────────────────────────────────────

@models_manager_router.get("/list")
async def list_packages(
    service: PipelineService = Depends(get_pipeline_service),
) -> list[dict]:
    """List all model packages found in the current models_dir (including invalid ones)."""
    models_dir = service.settings.models_dir
    if not models_dir:
        return []
    from app.models_manager.package import scan_models_dir, _load_package
    from pathlib import Path
    path = Path(models_dir)
    if not path.exists():
        return []
    result = []
    for sub in sorted(path.iterdir()):
        if not sub.is_dir():
            continue
        pkg = _load_package(sub)
        if pkg is not None:
            result.append(_package_to_dict(pkg))
    return result


@models_manager_router.get("/catalog")
async def get_catalog() -> list[dict]:
    """Return the official model catalog."""
    from app.models_manager.official_catalog import get_catalog
    return [m.to_dict() for m in get_catalog()]


class AddFolderRequest(BaseModel):
    folder_path: str


@models_manager_router.post("/scan")
async def rescan_models(
    service: PipelineService = Depends(get_pipeline_service),
) -> dict:
    """Rescan models_dir and rebuild the plugin registry."""
    models_dir = service.settings.models_dir
    if not models_dir:
        raise HTTPException(status_code=400, detail="models_dir is not configured")
    try:
        from app.plugins.builtin.presets import build_builtin_registry
        build_builtin_registry(service.settings)
        from app.models_manager.package import scan_models_dir
        packages = scan_models_dir(models_dir)
        return {"ok": True, "found": len(packages)}
    except Exception as exc:
        logger.exception("Rescan failed")
        raise HTTPException(status_code=500, detail=str(exc))


@models_manager_router.post("/add")
async def add_package_folder(
    body: AddFolderRequest,
    service: PipelineService = Depends(get_pipeline_service),
) -> dict:
    """
    Validate a model package at folder_path and, if valid, set models_dir
    to its parent directory (or add it alongside existing models).
    """
    folder = Path(body.folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=422, detail=f"Folder not found: {folder}")

    from app.models_manager.package import _load_package
    pkg = _load_package(folder)
    if pkg is None:
        raise HTTPException(status_code=422, detail="No metadata.json found in folder")
    if not pkg.is_valid:
        raise HTTPException(status_code=422, detail=f"Invalid package: {pkg.errors}")

    # If models_dir not set yet, use parent as models_dir
    if not service.settings.models_dir:
        new_settings = service.settings.model_copy(
            update={"models_dir": str(folder.parent)}
        )
        service.update_settings(new_settings)

    return {"ok": True, "id": pkg.id, "name": pkg.name}


@models_manager_router.post("/download/{catalog_id}")
async def start_download(
    catalog_id: str,
    service: PipelineService = Depends(get_pipeline_service),
) -> StreamingResponse:
    """
    Clone or pull the git repo for the given catalog entry.
    Streams progress as newline-delimited text (SSE-compatible).
    After completion, sets models_dir and rescans.
    """
    from app.models_manager.official_catalog import get_by_id
    entry = get_by_id(catalog_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Catalog entry not found: {catalog_id}")

    # Destination: user data dir / models / {catalog_id}
    from app.core import get_user_data_dir
    dest = get_user_data_dir() / "models" / catalog_id
    models_subdir = dest / entry.models_subdir
    do_pull = service.settings.auto_update_models

    async def _stream():
        try:
            from app.models_manager.downloader import clone_or_pull
            async for line in clone_or_pull(entry.repo_url, dest, do_pull=do_pull):
                yield line + "\n"

            # After successful download, set models_dir and rescan
            new_settings = service.settings.model_copy(
                update={"models_dir": str(models_subdir)}
            )
            service.update_settings(new_settings)
            yield f"models_dir_set:{models_subdir}\n"
            yield "complete\n"
        except Exception as exc:
            logger.exception("Download failed for %s", catalog_id)
            yield f"error:{exc}\n"

    return StreamingResponse(_stream(), media_type="text/plain")


@models_manager_router.get("/download-dest/{catalog_id}")
async def get_download_dest(catalog_id: str) -> dict:
    """Returns the default destination path for a catalog entry download."""
    from app.core import get_user_data_dir
    from app.models_manager.official_catalog import get_by_id
    entry = get_by_id(catalog_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Not found: {catalog_id}")
    dest = get_user_data_dir() / "models" / catalog_id
    models_subdir = dest / entry.models_subdir
    return {
        "repo_dest": str(dest),
        "models_dir": str(models_subdir),
        "is_installed": (dest / ".git").exists(),
    }
