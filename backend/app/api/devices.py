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
    result = [d.to_dict() for d in devices]
    # Own device always first, then by risk score descending
    result.sort(key=lambda d: (not d.get("is_self", False), -d.get("risk_score", 0)))
    return result


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


def _grab_banner(ip: str, port: int) -> str | None:
    import socket
    try:
        with socket.create_connection((ip, port), timeout=2) as s:
            # Send a bare newline — enough for most text protocols to respond
            s.send(b"\r\n")
            data = s.recv(256)
            return data.decode("utf-8", errors="replace").strip()[:160]
    except Exception:
        return None


def _check_http(ip: str, port: int, https: bool = False) -> dict | None:
    import re, urllib.request, ssl
    try:
        proto = "https" if https else "http"
        url = f"{proto}://{ip}:{port}/"
        ctx = ssl.create_default_context() if https else None
        if ctx:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "AnomalyNet/1.0 (network scanner)"})
        with urllib.request.urlopen(req, timeout=3, context=ctx) as resp:
            server = resp.headers.get("Server", "")
            ct = resp.headers.get("Content-Type", "")
            html = resp.read(4096).decode("utf-8", errors="replace") if "html" in ct else ""
            tm = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.DOTALL)
            return {
                "reachable": True,
                "status": resp.status,
                "server": server[:80],
                "title": tm.group(1).strip()[:80] if tm else "",
                "url": url,
            }
    except Exception:
        return None


def _check_rtsp(ip: str) -> bool:
    import socket
    try:
        with socket.create_connection((ip, 554), timeout=2) as s:
            s.send(b"OPTIONS * RTSP/1.0\r\nCSeq: 1\r\n\r\n")
            resp = s.recv(256).decode("utf-8", errors="replace")
            return "RTSP" in resp or "200" in resp
    except Exception:
        return False


def _get_ttl(ip: str) -> int | None:
    import platform, re, subprocess
    try:
        if platform.system() == "Windows":
            r = subprocess.run(["ping", "-n", "1", "-w", "1000", ip],
                               capture_output=True, text=True, timeout=4)
            m = re.search(r"TTL=(\d+)", r.stdout, re.I)
        else:
            r = subprocess.run(["ping", "-c", "1", "-W", "1", ip],
                               capture_output=True, text=True, timeout=4)
            m = re.search(r"ttl=(\d+)", r.stdout, re.I)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _do_full_inspect(ip: str, device_type: str, open_ports: list[int]) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    services = []
    web_urls = []
    rtsp_url = None
    os_guess = None

    checks: dict = {
        "http_80":   (lambda: _check_http(ip, 80)),
        "http_8080": (lambda: _check_http(ip, 8080)),
        "http_8888": (lambda: _check_http(ip, 8888)),
        "https_443": (lambda: _check_http(ip, 443, https=True)),
        "ssh_22":    (lambda: _grab_banner(ip, 22)),
        "ftp_21":    (lambda: _grab_banner(ip, 21)),
        "telnet_23": (lambda: _grab_banner(ip, 23)),
        "rtsp_554":  (lambda: _check_rtsp(ip)),
        "ttl":       (lambda: _get_ttl(ip)),
    }
    results: dict = {}
    with ThreadPoolExecutor(max_workers=9) as pool:
        futs = {pool.submit(fn): key for key, fn in checks.items()}
        for f in as_completed(futs, timeout=6):
            key = futs[f]
            try:
                results[key] = f.result()
            except Exception:
                results[key] = None

    # Process HTTP
    for key, port, https in [("http_80", 80, False), ("http_8080", 8080, False),
                              ("http_8888", 8888, False), ("https_443", 443, True)]:
        r = results.get(key)
        if r and r.get("reachable"):
            web_urls.append(r["url"])
            proto = "HTTPS" if https else "HTTP"
            services.append({
                "port": port, "protocol": proto,
                "title": r.get("title", ""), "server": r.get("server", ""),
                "status": r.get("status"),
            })

    # SSH / FTP / Telnet
    for key, port, proto in [("ssh_22", 22, "SSH"), ("ftp_21", 21, "FTP"), ("telnet_23", 23, "Telnet")]:
        banner = results.get(key)
        if banner:
            services.append({"port": port, "protocol": proto, "banner": banner})

    # RTSP
    if results.get("rtsp_554"):
        rtsp_url = f"rtsp://{ip}:554/stream"
        services.append({"port": 554, "protocol": "RTSP", "banner": "RTSP stream available"})
    elif device_type == "iot_camera":
        rtsp_url = f"rtsp://{ip}:554/stream"  # common default even without confirmation

    # OS guess from TTL
    ttl = results.get("ttl")
    if ttl:
        if ttl >= 120:
            os_guess = f"Windows (TTL={ttl})"
        elif ttl >= 55:
            os_guess = f"Linux / macOS (TTL={ttl})"
        elif ttl >= 28:
            os_guess = f"Роутер / IoT (TTL={ttl})"
        else:
            os_guess = f"Неизвестно (TTL={ttl})"

    return {
        "ip": ip,
        "os_guess": os_guess,
        "services": services,
        "web_urls": web_urls,
        "rtsp_url": rtsp_url,
    }


@devices_router.post("/devices/{mac}/inspect")
async def inspect_device(
    mac: str,
    tracker: DeviceTracker = Depends(get_device_tracker),
) -> dict:
    """Full service inspection: HTTP banners, SSH/FTP/RTSP detection, OS guess from TTL."""
    dev = tracker.get_device_by_mac(mac)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not found")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _do_full_inspect, dev.ip, dev.device_type, dev.open_ports
    )
    # Merge newly found ports back into device
    found_ports = {s["port"] for s in result["services"]}
    if found_ports:
        dev.open_ports = sorted(set(dev.open_ports) | found_ports)
    return result


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
