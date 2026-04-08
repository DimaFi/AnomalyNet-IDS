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


def _open_browser() -> None:
    """Wait a moment for uvicorn to start, then open the browser."""
    time.sleep(1.8)
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    import uvicorn

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="warning",
    )
