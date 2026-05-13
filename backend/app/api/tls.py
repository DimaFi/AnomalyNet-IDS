from __future__ import annotations

from fastapi import APIRouter, Query, Request

tls_router = APIRouter(prefix="/api/tls")


def _monitor(request: Request):
    return getattr(request.app.state, "tls_monitor", None)


def _adapter(request: Request):
    """Return the capture adapter if it exposes TLS stats (linux_live only)."""
    svc = getattr(request.app.state, "pipeline_service", None)
    if svc is None:
        return None
    return getattr(svc, "_adapter", None)


@tls_router.get("/stats")
def get_tls_stats(request: Request = None):  # type: ignore[assignment]
    """Combined TLS statistics: monitor counters + parse counters + adapter counters."""
    m = _monitor(request)
    if m is None:
        return {"available": False, "monitor": {}, "parser": {}, "adapter": {}}

    monitor_stats = m.get_stats()

    from app.tls.fingerprint import get_parse_stats
    parser_stats = get_parse_stats()

    adapter = _adapter(request)
    adapter_stats = adapter.get_tls_stats() if adapter and hasattr(adapter, "get_tls_stats") else {}

    return {
        "available": True,
        "monitor": monitor_stats,
        "parser": parser_stats,
        "adapter": adapter_stats,
    }


@tls_router.get("/profiles")
def get_tls_profiles(
    src_ip: str | None = Query(default=None, description="Filter by src IP"),
    request: Request = None,  # type: ignore[assignment]
):
    """Return JA4 profiles accumulated by TLSMonitor.

    Without src_ip: all IPs (dict ip → {ja4 → {count, first_seen, last_seen}}).
    With src_ip: profile for one IP only.
    """
    m = _monitor(request)
    if m is None:
        return {"available": False, "profiles": {}}

    if src_ip:
        return {"available": True, "profiles": {src_ip: m.get_profile(src_ip)}}

    profiles = m.get_all_profiles()
    # Serialize datetimes to ISO strings
    result: dict = {}
    for ip, fp_map in profiles.items():
        result[ip] = {}
        for ja4, entry in fp_map.items():
            result[ip][ja4] = {
                "count":      entry.get("count", 0),
                "first_seen": entry["first_seen"].isoformat() if hasattr(entry.get("first_seen"), "isoformat") else str(entry.get("first_seen", "")),
                "last_seen":  entry["last_seen"].isoformat()  if hasattr(entry.get("last_seen"),  "isoformat") else str(entry.get("last_seen",  "")),
            }

    return {"available": True, "profiles": result, "total_ips": len(result)}
