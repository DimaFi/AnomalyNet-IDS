"""
Re-exports BaseFirewall from security/blocker.py for use via the platform layer.

The canonical implementation lives in app.security.blocker — we keep it there
so existing imports are not broken. This file is a thin re-export.
"""

from app.security.blocker import BaseFirewall, MockFirewall  # noqa: F401
