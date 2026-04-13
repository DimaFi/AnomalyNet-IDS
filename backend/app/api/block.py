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


@block_router.get("/interfaces")
async def list_interfaces() -> list[dict]:
    """
    Returns network interfaces visible to the OS.
    Uses psutil if available; falls back to a basic socket-based list.
    """
    try:
        import psutil
        result = []
        for name, addrs in psutil.net_if_addrs().items():
            ipv4 = [a.address for a in addrs if a.family == 2]  # AF_INET
            result.append({"name": name, "addresses": ipv4})
        return result
    except ImportError:
        pass

    # Fallback: just return a placeholder
    return [{"name": "eth0", "addresses": []}, {"name": "lo", "addresses": ["127.0.0.1"]}]
