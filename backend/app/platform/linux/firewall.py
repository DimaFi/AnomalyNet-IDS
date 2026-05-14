"""
Re-exports LinuxFirewall from security/blocker.py for use via the platform layer.

The canonical implementation lives in app.security.blocker — we keep it there
so existing imports (from app.security.blocker import LinuxFirewall) are not broken.
"""

from app.security.blocker import LinuxFirewall  # noqa: F401
