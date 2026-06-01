"""
Access-key gate for public (Cloudflare tunnel) exposure.

The panel has no login. When public access is enabled we require a secret key —
but ONLY for requests that arrive through the Cloudflare tunnel (identified by
the CF-Ray / CF-Connecting-IP headers Cloudflare injects). Direct local/LAN
requests are not gated, so the local user is never locked out.

The key is embedded in the public URL/QR (?key=...), so for the owner it's just
"scan and go", while random scanners hitting the tunnel URL get a 403.
"""

from __future__ import annotations

import logging
import secrets

from app.core import get_user_data_dir

_log = logging.getLogger("app.remote.gate")

_key: str = ""
_enabled: bool = False
_keyfile = get_user_data_dir() / "remote_public_key.txt"


def _persist() -> None:
    try:
        _keyfile.parent.mkdir(parents=True, exist_ok=True)
        if _enabled and _key:
            _keyfile.write_text(_key, encoding="utf-8")
        else:
            _keyfile.unlink(missing_ok=True)
    except Exception as exc:
        _log.debug("[gate] persist error: %s", exc)


def generate_key() -> str:
    """Create a fresh key and enable the gate."""
    global _key, _enabled
    _key = secrets.token_urlsafe(12)
    _enabled = True
    _persist()
    return _key


def disable() -> None:
    global _enabled
    _enabled = False
    _persist()


def current_key() -> str:
    return _key


def is_enabled() -> bool:
    return _enabled and bool(_key)


def is_via_tunnel(headers) -> bool:
    """True if the request arrived through the Cloudflare tunnel."""
    return ("cf-ray" in headers) or ("cf-connecting-ip" in headers)


def request_allowed(headers, query_key: str, cookie_key: str) -> bool:
    """Gate decision. Only tunnel requests are checked."""
    if not is_enabled() or not is_via_tunnel(headers):
        return True
    provided = query_key or cookie_key or ""
    return bool(_key) and provided == _key
