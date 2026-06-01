"""
Public remote access API — Cloudflare quick tunnel + access key.

POST /api/remote/public/enable   → start tunnel, generate key, return public URL
POST /api/remote/public/disable  → stop tunnel, clear key
GET  /api/remote/public/status   → { running, url, enabled, public_url }
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter

from app.remote import gate
from app.remote.tunnel import tunnel

remote_router = APIRouter(prefix="/api/remote/public")
_log = logging.getLogger("app.api.remote")

PORT = 8000


def _public_url(url: str) -> str:
    key = gate.current_key()
    if url and key:
        return f"{url}/?key={key}"
    return url


@remote_router.get("/status")
def status() -> dict:
    st = tunnel.status()
    return {
        "running": st["running"],
        "url": st["url"],
        "enabled": gate.is_enabled(),
        "public_url": _public_url(st["url"]) if st["running"] else "",
    }


@remote_router.post("/enable")
async def enable() -> dict:
    """Download cloudflared if needed, start the tunnel, and gate it with a key."""
    try:
        key = gate.generate_key()
        # tunnel.start blocks until the URL is ready — run off the event loop
        st = await asyncio.get_event_loop().run_in_executor(None, lambda: tunnel.start(PORT))
        return {
            "ok": True,
            "running": True,
            "url": st["url"],
            "public_url": _public_url(st["url"]),
            "key": key,
        }
    except Exception as exc:
        gate.disable()
        _log.warning("[remote] enable failed: %s", exc)
        return {"ok": False, "error": str(exc)}


@remote_router.post("/disable")
async def disable() -> dict:
    await asyncio.get_event_loop().run_in_executor(None, tunnel.stop)
    gate.disable()
    return {"ok": True, "running": False}
