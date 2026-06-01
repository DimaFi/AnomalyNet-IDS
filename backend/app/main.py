from __future__ import annotations

import asyncio
import json
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

try:
    import setproctitle
    setproctitle.setproctitle("AnomalyNet IDS")
except Exception:
    pass

import platform as _plat
if _plat.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("AnomalyNet IDS")
    except Exception:
        pass


def _get_version() -> str:
    """Read version from git tag. Handles shallow clones (--depth=1)."""
    from app.core import git_safe
    repo = Path(__file__).parent.parent.parent
    try:
        r = subprocess.run(
            git_safe(["git", "describe", "--tags", "--always"]),
            cwd=repo, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            val = r.stdout.strip().lstrip("v")
            if "." in val:          # "2.3.0" or "2.3.0-3-gabcdef" → real version
                return val.split("-")[0]   # strip "-3-gabcdef" suffix → "2.3.0"
    except Exception:
        pass
    # Fallback: list all tags sorted by version, take latest
    try:
        r = subprocess.run(
            git_safe(["git", "tag", "--sort=-version:refname"]),
            cwd=repo, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            tags = [t.strip().lstrip("v") for t in r.stdout.splitlines() if t.strip()]
            if tags:
                return tags[0]
    except Exception:
        pass
    return "dev"


def _download_oui_sync(out_file: Path) -> None:
    """Download IEEE OUI database to out_file. Blocking — run in executor."""
    import csv
    import io
    import json as _j
    import urllib.request
    url = "https://standards-oui.ieee.org/oui/oui.csv"
    req = urllib.request.Request(url, headers={"User-Agent": "AnomalyNet/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    entries = []
    for row in csv.DictReader(io.StringIO(raw)):
        a = row.get("Assignment", "").strip().upper()
        v = row.get("Organization Name", "").strip()
        if len(a) == 6 and v:
            entries.append({"macPrefix": f"{a[0:2]}:{a[2:4]}:{a[4:6]}", "vendorName": v})
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(_j.dumps(entries, ensure_ascii=False), encoding="utf-8")


async def _bg_oui_download(out_file: Path) -> None:
    import logging as _lg
    _log = _lg.getLogger("app.discovery.oui")
    _log.info("OUI database not found — downloading from IEEE (background)…")
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _download_oui_sync, out_file)
        _log.info("OUI database downloaded — vendor lookup enabled")
    except Exception as exc:
        _log.warning("OUI download failed (vendor lookup limited): %s", exc)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.autostart import autostart_router
from app.api.shortcuts import shortcuts_router
from app.api.block import block_router, _detect_best_interface_by_traffic
from app.api.devices import devices_router, ws_devices_endpoint
from app.api.dns import dns_router
from app.api.models_manager import models_manager_router
from app.api.plugins import plugins_router
from app.api.routes import router
from app.api.system import system_router
from app.api.tls import tls_router
from app.api.update import update_router
from app.core import APP_ROOT
from app.discovery.scanner import NetworkScanner
from app.discovery.tracker import DeviceTracker
from app.dns.monitor import DnsMonitor
from app.pipeline.service import PipelineService
from app.storage.json_store import JsonFileStore


def _auto_select_interface_if_needed(service: PipelineService) -> None:
    """If no interface is configured, auto-detect the busiest one and save it."""
    s = service.settings
    if s.interface_name and s.interface_name not in ("eth0", ""):
        return  # already user-configured
    if s.interface_names:
        return  # multi-interface already set
    best = _detect_best_interface_by_traffic()
    if best and best != s.interface_name:
        import logging
        logging.getLogger(__name__).info("Auto-selected interface: %s", best)
        service.update_settings(s.model_copy(update={"interface_name": best}))


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = JsonFileStore(APP_ROOT)
    service = PipelineService(store)
    app.state.pipeline_service = service

    # Инициализация plugin registry с builtin плагинами
    try:
        from app.plugins.builtin.presets import build_builtin_registry
        build_builtin_registry(service.settings)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Plugin registry init failed: %s", exc)

    # Auto-detect best interface if none configured
    _auto_select_interface_if_needed(service)

    # Device discovery
    iface = service.settings.interface_name or None
    tracker = DeviceTracker()
    scanner = NetworkScanner(interface=iface)
    app.state.device_tracker = tracker
    app.state.network_scanner = scanner
    service.set_device_tracker(tracker)

    # Auto-download OUI vendor database if missing (needed for device type classification)
    _oui_file = APP_ROOT / "config" / "oui.json"
    if not _oui_file.exists():
        asyncio.create_task(_bg_oui_download(_oui_file))

    # DNS monitoring (runs in linux_live mode; gracefully no-op otherwise)
    dns_monitor = DnsMonitor()
    app.state.dns_monitor = dns_monitor
    service.set_dns_monitor(dns_monitor)

    # Wire DNS alert → history storage + device risk update
    import logging as _logging
    _dns_log = _logging.getLogger("app.dns.monitor")

    def _on_dns_alert(alert: dict) -> None:
        try:
            from app.dns.events import dns_alert_to_pipeline_event
            pipeline_event = dns_alert_to_pipeline_event(alert)
            store.append_history(pipeline_event)
        except Exception:
            _dns_log.exception("Failed to persist DNS alert to history")
        try:
            tracker.on_dns_alert(alert.get("src_ip", ""))
        except Exception:
            pass

    dns_monitor.set_alert_callback(_on_dns_alert)

    # TLS monitoring (platform-independent; fingerprint extraction requires linux_live)
    from app.tls.monitor import TLSMonitor
    tls_monitor = TLSMonitor()
    app.state.tls_monitor = tls_monitor
    service.set_tls_monitor(tls_monitor)

    _tls_log = _logging.getLogger("app.tls.monitor")

    def _on_tls_alert(alert: dict) -> None:
        try:
            from app.tls.events import tls_alert_to_pipeline_event
            pipeline_event = tls_alert_to_pipeline_event(alert)
            service.publish_external_event(pipeline_event)
        except Exception:
            _tls_log.exception("Failed to persist TLS alert to history")

    tls_monitor.set_alert_callback(_on_tls_alert)

    await service.start()
    scan_task = asyncio.create_task(scanner.start_background_scan(tracker=tracker, interval=60))
    try:
        yield
    finally:
        scan_task.cancel()
        await service.shutdown()


def _read_allow_remote() -> bool:
    """Read allow_remote_access from settings.json at startup (before lifespan)."""
    try:
        import json as _json
        cfg = APP_ROOT / "config" / "settings.json"
        if cfg.exists():
            return bool(_json.loads(cfg.read_text(encoding="utf-8")).get("allow_remote_access", False))
    except Exception:
        pass
    return False


_allow_remote = _read_allow_remote()

app = FastAPI(title="AnomalyNet API", version=_get_version(), lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_remote else [
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:8000", "http://localhost:8000",
    ],
    allow_credentials=not _allow_remote,   # credentials forbidden when origins=*
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(autostart_router)
app.include_router(shortcuts_router)
app.include_router(block_router)
app.include_router(devices_router)
app.include_router(dns_router)
app.include_router(system_router)
app.include_router(tls_router)
app.include_router(update_router)
app.include_router(plugins_router)
app.include_router(models_manager_router)

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
        # Serve real files (logo.png, favicon, etc.) if they exist in dist
        candidate = _DIST / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        # no-store: browser always re-fetches index.html, so new hashed assets load immediately
        return FileResponse(str(_DIST / "index.html"), headers={"Cache-Control": "no-store, no-cache"})


@app.websocket("/ws/devices")
async def devices_ws(websocket: WebSocket) -> None:
    tracker: DeviceTracker = websocket.app.state.device_tracker
    await ws_devices_endpoint(websocket, tracker)


@app.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    service: PipelineService = websocket.app.state.pipeline_service
    queue = service.subscribe()
    try:
        # Send initial snapshot capped to 200 items — avoid sending large payloads on slow servers
        snap = service.snapshot()
        snap_dict = snap.model_dump(mode="json")
        snap_dict["items"] = snap_dict["items"][:200]
        await websocket.send_text(json.dumps(snap_dict, ensure_ascii=False))
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

