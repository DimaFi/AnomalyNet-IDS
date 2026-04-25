from __future__ import annotations

from fastapi import APIRouter, Query, Request

dns_router = APIRouter(prefix="/api/dns")


def _monitor(request: Request):
    return getattr(request.app.state, "dns_monitor", None)


@dns_router.get("/recent")
def get_dns_recent(
    src_ip: str | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    request: Request = None,  # type: ignore[assignment]
):
    m = _monitor(request)
    if m is None:
        return {"items": [], "available": False}
    return {"items": m.get_recent(src_ip=src_ip, limit=limit), "available": True}


@dns_router.get("/top")
def get_dns_top(
    src_ip: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    request: Request = None,  # type: ignore[assignment]
):
    m = _monitor(request)
    if m is None:
        return {"domains": [], "available": False}
    return {"domains": m.get_top_domains(src_ip=src_ip, limit=limit), "available": True}


@dns_router.get("/alerts")
def get_dns_alerts(
    limit: int = Query(default=50, le=200),
    request: Request = None,  # type: ignore[assignment]
):
    m = _monitor(request)
    if m is None:
        return {"alerts": [], "available": False}
    return {"alerts": m.get_alerts(limit=limit), "available": True}


@dns_router.get("/device/{ip}/summary")
def get_device_dns_summary(ip: str, request: Request = None):  # type: ignore[assignment]
    m = _monitor(request)
    if m is None:
        return {"total_queries": 0, "alert_count": 0, "top_domains": [], "available": False}
    return {**m.get_device_summary(ip), "available": True}
