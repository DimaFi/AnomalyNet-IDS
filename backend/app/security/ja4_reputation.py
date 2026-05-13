"""
JA4 fingerprint reputation lookup.

Uses a local JSON database of known suspicious/malicious JA4 fingerprints.
Does NOT make any network requests — fully offline.

Usage:
    from app.security.ja4_reputation import lookup_ja4_reputation
    rep = lookup_ja4_reputation(ja4_string)
    if rep:
        # rep = {"label": ..., "severity": ..., "score_boost": ..., "description": ...}
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent / "ja4_reputation.json"

_lock = threading.Lock()
_db: dict[str, dict] | None = None  # lazy-loaded


def _load_db() -> dict[str, dict]:
    global _db
    if _db is not None:
        return _db
    with _lock:
        if _db is not None:
            return _db
        if not _DB_PATH.exists():
            _log.warning("JA4 reputation database not found at %s — reputation checks disabled", _DB_PATH)
            _db = {}
            return _db
        try:
            raw = json.loads(_DB_PATH.read_text(encoding="utf-8"))
            _db = raw.get("fingerprints", {})
            _log.info("JA4 reputation DB loaded: %d entries from %s", len(_db), _DB_PATH)
        except Exception as exc:
            _log.error("Failed to load JA4 reputation DB: %s", exc)
            _db = {}
        return _db


def lookup_ja4_reputation(ja4: str | None) -> Optional[dict]:
    """Look up a JA4 fingerprint in the local reputation database.

    Returns a dict with {label, severity, score_boost, source, description}
    or None if not found or ja4 is empty.

    Thread-safe, never raises.
    """
    if not ja4:
        return None
    try:
        db = _load_db()
        return db.get(ja4)
    except Exception as exc:
        _log.debug("JA4 reputation lookup error: %s", exc)
        return None


def get_db_size() -> int:
    """Return number of fingerprints in the loaded database."""
    try:
        return len(_load_db())
    except Exception:
        return 0
