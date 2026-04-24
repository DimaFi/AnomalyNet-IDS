from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import Request

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.dependencies import get_device_tracker
from app.discovery.tracker import DeviceTracker

logger = logging.getLogger(__name__)

devices_router = APIRouter(prefix="/api")

_ws_clients: list[asyncio.Queue] = []
_ws_lock = asyncio.Lock()


async def broadcast_devices(payload: dict) -> None:
    async with _ws_lock:
        dead = []
        for q in _ws_clients:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            _ws_clients.remove(q)


# ── REST endpoints ────────────────────────────────────────────

@devices_router.get("/devices")
async def list_devices(
    suspicious_only: bool = Query(False),
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> list[dict]:
    devices = tracker.get_all_devices()
    if suspicious_only:
        devices = [d for d in devices if d.is_suspicious]
    return [d.to_dict() for d in devices]


@devices_router.get("/devices/stats")
async def device_stats(
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> dict:
    return tracker.get_stats()


@devices_router.post("/devices/scan")
async def trigger_scan(
    request: Request,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> dict:
    scanner = getattr(request.app.state, "network_scanner", None)

    if scanner is None:
        return {"success": False, "error": "Scanner not available"}

    try:
        loop = asyncio.get_event_loop()
        devices = await loop.run_in_executor(None, scanner.scan_once)
        tracker.merge_scan_results(devices)
        payload = {
            "type": "devices_update",
            "devices": [d.to_dict() for d in tracker.get_all_devices()],
            "stats": tracker.get_stats(),
        }
        await broadcast_devices(payload)
        return {"success": True, "found": len(devices)}
    except Exception as exc:
        logger.warning("Scan failed: %s", exc)
        return {"success": False, "error": str(exc)}


@devices_router.get("/devices/{mac}/history")
async def device_alert_history(
    mac: str,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> list[dict]:
    dev = tracker.get_device_by_mac(mac)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return tracker.get_alert_history(mac)


class LabelRequest(BaseModel):
    custom_name: str = ""
    device_type: str = "unknown"


@devices_router.post("/devices/{mac}/label")
async def label_device(
    mac: str,
    body: LabelRequest,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> dict:
    dev = tracker.get_device_by_mac(mac)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not found")
    tracker.set_label(mac, body.custom_name, body.device_type)
    return {"success": True}


@devices_router.post("/devices/{mac}/whitelist")
async def whitelist_device(
    mac: str,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> dict:
    dev = tracker.get_device_by_mac(mac)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not found")
    tracker.set_whitelisted(mac, True)
    return {"success": True}


@devices_router.delete("/devices/{mac}/whitelist")
async def unwhitelist_device(
    mac: str,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> dict:
    dev = tracker.get_device_by_mac(mac)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not found")
    tracker.set_whitelisted(mac, False)
    return {"success": True}


@devices_router.post("/devices/{mac}/reset")
async def reset_device(
    mac: str,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> dict:
    dev = tracker.get_device_by_mac(mac)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not found")
    tracker.reset_suspicious(mac)
    return {"success": True}


# ── WebSocket ─────────────────────────────────────────────────

async def ws_devices_endpoint(websocket: WebSocket, tracker: DeviceTracker) -> None:
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=20)
    async with _ws_lock:
        _ws_clients.append(queue)

    try:
        # Send initial snapshot
        payload = {
            "type": "devices_update",
            "devices": [d.to_dict() for d in tracker.get_all_devices()],
            "stats": tracker.get_stats(),
        }
        await websocket.send_json(payload)

        ping_counter = 0
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=5.0)
                await websocket.send_json(msg)
            except asyncio.TimeoutError:
                ping_counter += 1
                if ping_counter >= 4:  # ~20s keepalive
                    await websocket.send_json({"type": "ping"})
                    ping_counter = 0
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        async with _ws_lock:
            if queue in _ws_clients:
                _ws_clients.remove(queue)
