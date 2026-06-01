"""
System resource stats endpoint.

GET /api/system/stats — CPU%, RAM, network I/O (KB/s), process memory, load level.
Uses psutil (already in requirements).
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_pipeline_service
from app.pipeline.service import PipelineService

system_router = APIRouter(prefix="/api/system")

_prev_net_time: float = 0.0
_prev_net_sent: int = 0
_prev_net_recv: int = 0


def _compute_load_level(cpu: float, ram: float, proc_cpu: float) -> str:
    """Return 'low', 'medium', 'high', or 'critical' based on resource usage."""
    worst = max(cpu, ram, proc_cpu)
    if worst >= 85:
        return "critical"
    if worst >= 60:
        return "high"
    if worst >= 40:
        return "medium"
    return "low"


@system_router.get("/stats")
def get_system_stats(
    request: Request,
) -> dict:
    global _prev_net_time, _prev_net_sent, _prev_net_recv
    try:
        import psutil
    except ImportError:
        return {"available": False, "error": "psutil not installed"}

    try:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()

        # Network I/O delta since last call
        net = psutil.net_io_counters()
        now = time.monotonic()
        dt = now - _prev_net_time if _prev_net_time > 0 else 1.0
        sent_kbps = (net.bytes_sent - _prev_net_sent) / dt / 1024 if _prev_net_time > 0 else 0.0
        recv_kbps = (net.bytes_recv - _prev_net_recv) / dt / 1024 if _prev_net_time > 0 else 0.0
        _prev_net_time = now
        _prev_net_sent = net.bytes_sent
        _prev_net_recv = net.bytes_recv

        # This process
        proc = psutil.Process()
        proc_cpu = proc.cpu_percent(interval=None)
        proc_ram_mb = proc.memory_info().rss / 1024 / 1024

        load_level = _compute_load_level(cpu, ram.percent, proc_cpu)

        # Pipeline stats (optional — graceful if not available)
        pipeline_stats: dict = {}
        try:
            service: PipelineService = request.app.state.pipeline_service
            snap = service.snapshot()
            db = service.debug_stats()
            pipeline_stats = {
                "events_total": db.uptime_events_total,
                "events_warning": db.events_by_label.get("warning", 0),
                "events_anomaly": db.events_by_label.get("anomaly", 0),
                "buffer_size": len(snap.items),
                "buffer_max": 500,
            }
        except Exception:
            pass

        return {
            "available": True,
            "cpu_percent": round(cpu, 1),
            "ram_used_mb": round(ram.used / 1024 / 1024),
            "ram_total_mb": round(ram.total / 1024 / 1024),
            "ram_percent": round(ram.percent, 1),
            "net_sent_kbps": round(max(sent_kbps, 0), 1),
            "net_recv_kbps": round(max(recv_kbps, 0), 1),
            "process_cpu_percent": round(proc_cpu, 1),
            "process_ram_mb": round(proc_ram_mb, 1),
            "load_level": load_level,
            **pipeline_stats,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


@system_router.get("/access-info")
def get_access_info(
    service: PipelineService = Depends(get_pipeline_service),
) -> dict:
    """Remote-access info: whether it's enabled + the LAN IPs the panel is
    reachable at. The frontend builds http://<ip>:<port> + a QR code from this.
    """
    import socket

    enabled = bool(getattr(service.settings, "allow_remote_access", False))

    def _rank(ip: str) -> int:
        # Prefer real home/office LAN ranges; demote Docker/WSL/Hyper-V (172.16-31).
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172."):
            try:
                second = int(ip.split(".")[1])
                if 16 <= second <= 31:
                    return 3
            except Exception:
                pass
        return 2

    # Default-route IP (the interface that actually reaches the internet/LAN).
    route_ip = ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        route_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    found: set[str] = set()
    if route_ip and not route_ip.startswith("127."):
        found.add(route_ip)
    try:
        import psutil
        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if (a.family == socket.AF_INET
                        and not a.address.startswith("127.")
                        and not a.address.startswith("169.254.")):
                    found.add(a.address)
    except Exception:
        pass

    # Sort by rank; if the default-route IP is a real LAN IP, force it first.
    ips = sorted(found, key=lambda ip: (_rank(ip), ip))
    if route_ip in ips and _rank(route_ip) < 3:
        ips.remove(route_ip)
        ips.insert(0, route_ip)

    primary = ips[0] if ips else ""
    return {"enabled": enabled, "primary_ip": primary, "lan_ips": ips}
