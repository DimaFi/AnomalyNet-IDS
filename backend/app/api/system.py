"""
System resource stats endpoint.

GET /api/system/stats — CPU%, RAM, network I/O (KB/s), process memory.
Uses psutil (already in requirements). Non-blocking.
"""
from __future__ import annotations

import time

from fastapi import APIRouter

system_router = APIRouter(prefix="/api/system")

_prev_net_time: float = 0.0
_prev_net_sent: int = 0
_prev_net_recv: int = 0


@system_router.get("/stats")
def get_system_stats() -> dict:
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
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}
