"""
AnomalyNet launcher — entrypoint for the packaged executable.

When frozen by PyInstaller:
- sys._MEIPASS contains unpacked bundle files
- We redirect APP_ROOT to the bundle path so config/ and shared/ are found
- uvicorn starts on 127.0.0.1:8000
- Browser opens automatically
"""
from __future__ import annotations

import os
import sys
import time
import threading
import webbrowser

# ── Resolve bundle root (works both frozen and dev) ──────────
if getattr(sys, "frozen", False):
    BUNDLE_DIR = sys._MEIPASS          # type: ignore[attr-defined]
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

# Make sure 'app' package is importable when frozen
if BUNDLE_DIR not in sys.path:
    sys.path.insert(0, BUNDLE_DIR)

# ── Override APP_ROOT so JsonFileStore / core.py find configs ─
os.environ.setdefault("ANOMALYNET_APP_ROOT", BUNDLE_DIR)


def _read_remote_access() -> bool:
    try:
        import json as _json
        cfg = os.path.join(BUNDLE_DIR, "config", "settings.json")
        if os.path.exists(cfg):
            return bool(_json.loads(open(cfg, encoding="utf-8").read()).get("allow_remote_access", False))
    except Exception:
        pass
    return False


def _open_browser(host: str) -> None:
    """Wait a moment for uvicorn to start, then open the browser."""
    time.sleep(1.8)
    webbrowser.open(f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:8000")


if __name__ == "__main__":
    import uvicorn

    _remote = _read_remote_access()
    _host = "0.0.0.0" if _remote else "127.0.0.1"

    threading.Thread(target=_open_browser, args=(_host,), daemon=True).start()

    uvicorn.run(
        "app.main:app",
        host=_host,
        port=8000,
        log_level="warning",
    )
