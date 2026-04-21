from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.block import block_router
from app.api.routes import router
from app.api.update import update_router
from app.core import APP_ROOT
from app.pipeline.service import PipelineService
from app.storage.json_store import JsonFileStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = JsonFileStore(APP_ROOT)
    service = PipelineService(store)
    app.state.pipeline_service = service
    await service.start()
    try:
        yield
    finally:
        await service.shutdown()


app = FastAPI(title="AnomalyNet API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(block_router)
app.include_router(update_router)

# Serve built frontend in production / packaged mode
_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str = "") -> FileResponse:
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        return FileResponse(str(_DIST / "index.html"))


@app.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    service: PipelineService = websocket.app.state.pipeline_service
    queue = service.subscribe()
    try:
        await websocket.send_text(json.dumps(service.snapshot().model_dump(mode="json"), ensure_ascii=False))
        while True:
            try:
                # Wait up to 20s for a new event; send a keepalive ping if idle
                item = await asyncio.wait_for(queue.get(), timeout=20.0)
                await websocket.send_text(json.dumps(item.model_dump(mode="json"), ensure_ascii=False))
            except asyncio.TimeoutError:
                # No events — send ping to keep connection alive
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        service.unsubscribe(queue)
    finally:
        service.unsubscribe(queue)
