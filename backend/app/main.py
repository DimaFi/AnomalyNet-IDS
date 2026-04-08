from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.block import block_router
from app.api.routes import router
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


app = FastAPI(title="Traffic Analysis Local API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(block_router)


@app.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    service: PipelineService = websocket.app.state.pipeline_service
    queue = service.subscribe()
    try:
        await websocket.send_text(json.dumps(service.snapshot().model_dump(mode="json"), ensure_ascii=False))
        while True:
            item = await queue.get()
            await websocket.send_text(json.dumps(item.model_dump(mode="json"), ensure_ascii=False))
    except WebSocketDisconnect:
        service.unsubscribe(queue)
    finally:
        service.unsubscribe(queue)
