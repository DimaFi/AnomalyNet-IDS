from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_OUI_FILE = Path(__file__).parent.parent.parent.parent / "config" / "oui.json"


class OUILookup:
    """MAC OUI → vendor name, lazy-loaded singleton."""

    def __init__(self) -> None:
        self._table: dict[str, str] = {}
        self._loaded = False
        self._lock = threading.Lock()

    def _load(self) -> None:
        if not _OUI_FILE.exists():
            logger.warning("OUI database not found at %s — vendor lookup disabled. Run scripts/download_oui.py", _OUI_FILE)
            return
        try:
            data: list[dict] = json.loads(_OUI_FILE.read_text(encoding="utf-8"))
            for entry in data:
                prefix = entry.get("macPrefix", "").upper().replace("-", ":").strip()
                vendor = entry.get("vendorName", "").strip()
                if prefix and vendor:
                    self._table[prefix] = vendor
            logger.info("OUI database loaded: %d entries", len(self._table))
        except Exception as exc:
            logger.warning("Failed to load OUI database: %s", exc)

    def lookup(self, mac: str) -> str:
        with self._lock:
            if not self._loaded:
                self._loaded = True
                self._load()

        if not self._table:
            return "Unknown"

        normalized = mac.upper().replace("-", ":").replace(".", ":")
        parts = normalized.split(":")
        if len(parts) < 3:
            return "Unknown"

        prefix = ":".join(parts[:3])
        return self._table.get(prefix, "Unknown")


_instance: OUILookup | None = None
_instance_lock = threading.Lock()


def get_oui_lookup() -> OUILookup:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = OUILookup()
    return _instance
