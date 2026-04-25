"""
Block API — iptables integration and network interface discovery.

POST /api/block    — insert iptables DROP rule for an IP address
GET  /api/interfaces — list available network interfaces
"""

from __future__ import annotations

import asyncio
import ipaddress

from fastapi import APIRouter, Depends, HTTPException

from app.contracts.schemas import BlockRequest, BlockResponse
from app.dependencies import get_pipeline_service
from app.pipeline.service import PipelineService


block_router = APIRouter(prefix="/api")


@block_router.post("/block", response_model=BlockResponse)
async def block_ip(
    payload: BlockRequest,
    service: PipelineService = Depends(get_pipeline_service),
) -> BlockResponse:
    """
    Inserts an iptables INPUT DROP rule for the given IP address.
    Requires root privileges or CAP_NET_ADMIN on Linux.
    On non-Linux systems the request is accepted but iptables is unavailable.
    """
    ip = payload.ip_address.strip()

    # Validate IPv4
    try:
        ipaddress.IPv4Address(ip)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid IPv4 address: {ip!r}")

    success = await service.block_ip(ip)
    if success:
        return BlockResponse(
            ip_address=ip,
            blocked=True,
            message=f"iptables: DROP rule added for {ip}",
        )
    else:
        # Not an error — may just be non-Linux / no privileges; return gracefully
        return BlockResponse(
            ip_address=ip,
            blocked=False,
            message="iptables not available or insufficient privileges",
        )


@block_router.get("/blocked-ips")
async def get_blocked_ips(
    service: PipelineService = Depends(get_pipeline_service),
) -> dict:
    """Returns all IPs currently blocked by this service via iptables."""
    registry = service.get_blocked_ips()
    return {
        "count": len(registry),
        "items": [{"ip": ip, "blocked_at": ts} for ip, ts in registry.items()],
    }


@block_router.delete("/blocked-ips/all")
async def unblock_all_ips(
    service: PipelineService = Depends(get_pipeline_service),
) -> dict:
    """Remove all iptables DROP rules added by this service."""
    count = await service.unblock_all_ips()
    return {"unblocked": count, "message": f"Removed {count} iptables rules"}


@block_router.delete("/blocked-ips/{ip}")
async def unblock_ip(
    ip: str,
    service: PipelineService = Depends(get_pipeline_service),
) -> dict:
    """Remove iptables DROP rule for a specific IP."""
    try:
        ipaddress.IPv4Address(ip)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid IPv4: {ip!r}")
    success = await service.unblock_ip(ip)
    return {"ip": ip, "unblocked": success}


@block_router.post("/block/rollback")
async def rollback_rules(
    service: PipelineService = Depends(get_pipeline_service),
) -> dict:
    """
    Restore iptables state from the last snapshot taken before blocking started.
    Resets all ANOMALYNET rules to the state at the time of the first block call.
    """
    ok = service.rollback_firewall()
    if ok:
        return {"success": True, "message": "iptables restored from snapshot"}
    return {"success": False, "message": "No backup found or iptables-restore failed"}


@block_router.get("/blocking/status")
async def blocking_status(
    service: PipelineService = Depends(get_pipeline_service),
) -> dict:
    """
    Returns the current state of the blocking subsystem:
    platform, iptables availability, ip_forward, current mode, snapshot, warnings.
    """
    return service.get_blocking_status()


async def _detect_default_interface() -> str:
    """Returns the interface used for the default route (e.g. enp0s3, eth0)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "route", "get", "8.8.8.8",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        line = stdout.decode(errors="ignore")
        # Output: "8.8.8.8 via 1.2.3.1 dev eth0 src ..."
        parts = line.split()
        idx = parts.index("dev") if "dev" in parts else -1
        if idx >= 0 and idx + 1 < len(parts):
            return parts[idx + 1]
    except Exception:
        pass
    return ""


def _detect_best_interface_by_traffic() -> str:
    """
    Returns the interface name with the most total traffic (bytes_recv + bytes_sent).
    Ignores loopback. Returns "" if psutil unavailable.
    """
    try:
        import psutil
        counters = psutil.net_io_counters(pernic=True)
        stats = psutil.net_if_stats()
        best = ""
        best_bytes = -1
        for name, cnt in counters.items():
            if name == "lo":
                continue
            if name in stats and not stats[name].isup:
                continue
            total = cnt.bytes_recv + cnt.bytes_sent
            if total > best_bytes:
                best_bytes = total
                best = name
        return best
    except Exception:
        return ""


@block_router.get("/interfaces")
async def list_interfaces() -> list[dict]:
    """
    Returns all non-loopback network interfaces with IPv4 addresses.
    is_default  — interface used for the default route
    is_recommended — interface with most traffic (best for capture)
    bytes_total — bytes_recv + bytes_sent (traffic indicator)
    """
    default_iface = await _detect_default_interface()
    recommended = _detect_best_interface_by_traffic()

    try:
        import psutil
        result = []
        counters = psutil.net_io_counters(pernic=True)
        stats = psutil.net_if_stats()
        for name, addrs in psutil.net_if_addrs().items():
            ipv4 = [a.address for a in addrs if a.family == 2]  # AF_INET
            if name == "lo" and ipv4 == ["127.0.0.1"]:
                continue
            is_up = stats[name].isup if name in stats else False
            cnt = counters.get(name)
            bytes_total = (cnt.bytes_recv + cnt.bytes_sent) if cnt else 0
            result.append({
                "name": name,
                "addresses": ipv4,
                "is_default": name == default_iface,
                "is_recommended": name == recommended,
                "is_up": is_up,
                "bytes_total": bytes_total,
            })
        # Sort: recommended first, then default, then by name
        result.sort(key=lambda x: (not x["is_recommended"], not x["is_default"], x["name"]))
        return result
    except ImportError:
        pass

    return [
        {"name": default_iface or "eth0", "addresses": [], "is_default": True,
         "is_recommended": True, "is_up": True, "bytes_total": 0},
    ]
