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


@devices_router.post("/devices/add")
async def add_device(
    body: AddDeviceRequest,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> dict:
    from app.discovery.scanner import arp_single_ip
    mac = body.mac.strip()
    # If no MAC provided, try ARP lookup
    if not mac:
        try:
            found = await asyncio.get_event_loop().run_in_executor(None, arp_single_ip, body.ip)
            mac = found or _generate_placeholder_mac(body.ip)
        except Exception:
            mac = _generate_placeholder_mac(body.ip)

    mac = mac.upper()
    dev = tracker.add_device_manual(
        ip=body.ip, mac=mac,
        custom_name=body.custom_name,
        device_type=body.device_type,
        vendor=body.vendor,
    )
    return {"success": True, "device": dev.to_dict()}


@devices_router.delete("/devices/{mac}")
async def remove_device(
    mac: str,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> dict:
    ok = tracker.remove_device(mac)
    if not ok:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True}


@devices_router.post("/devices/{mac}/probe")
async def probe_device(
    mac: str,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> dict:
    dev = tracker.get_device_by_mac(mac)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not found")
    from app.discovery.scanner import probe_host
    result = await asyncio.get_event_loop().run_in_executor(None, probe_host, dev.ip)
    # Update open ports in tracker
    if result["open_ports"]:
        dev.open_ports = result["open_ports"]
    return {"ip": dev.ip, **result}


def _generate_placeholder_mac(ip: str) -> str:
    parts = ip.split(".")
    try:
        octets = [int(p) for p in parts]
        return f"02:00:{octets[0]:02X}:{octets[1]:02X}:{octets[2]:02X}:{octets[3]:02X}"
    except Exception:
        import uuid
        raw = uuid.uuid4().hex[:12]
        return ":".join(raw[i:i+2].upper() for i in range(0, 12, 2))


@devices_router.get("/devices/{mac}/history")
async def device_alert_history(
    mac: str,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> list[dict]:
    dev = tracker.get_device_by_mac(mac)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return tracker.get_alert_history(mac)


class AddDeviceRequest(BaseModel):
    ip: str
    mac: str = ""
    custom_name: str = ""
    device_type: str = "unknown"
    vendor: str = "Unknown"


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
