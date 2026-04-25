"""
Platform-independent TLS behavioral monitor.

Accepts already-parsed fingerprint dicts (not raw packets).
Thread-safe — called from scapy capture thread via alert callback.

Alert types:
    NEW_TLS_FINGERPRINT         — fingerprint seen for the first time from this src_ip
    TOO_MANY_TLS_FINGERPRINTS   — >max_fingerprints_per_ip unique fps in the time window
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable

_log = logging.getLogger("app.tls.monitor")


class TLSMonitor:
    """Platform-independent TLS behavioral monitor.

    Usage:
        monitor = TLSMonitor()
        monitor.set_alert_callback(my_callback)
        # From any thread (e.g. scapy capture):
        fp = compute_tls_fingerprint_from_scapy(pkt)
        if fp:
            monitor.on_fingerprint(src_ip, dst_ip, dst_port, fp)
    """

    def __init__(
        self,
        max_fingerprints_per_ip: int = 8,
        window_seconds: int = 60,
    ) -> None:
        self._max_fps = max_fingerprints_per_ip
        self._window = window_seconds

        self._lock = threading.Lock()

        # ip → {ja4 → {"count": int, "first_seen": datetime, "last_seen": datetime}}
        self._profiles: dict[str, dict[str, dict]] = defaultdict(dict)

        # ip → datetime of last TOO_MANY alert (cooldown — one alert per window)
        self._too_many_cooldown: dict[str, datetime] = {}

        self._alert_callback: Callable[[dict], None] | None = None

    # ── public ───────────────────────────────────────────────────────────────

    def set_alert_callback(self, callback: Callable[[dict], None]) -> None:
        """Register a callable invoked on every alert. Must be fast and exception-safe."""
        self._alert_callback = callback

    def on_fingerprint(
        self,
        src_ip: str,
        dst_ip: str,
        dst_port: int,
        fingerprint: dict,
    ) -> dict | None:
        """Main entry point — platform-independent.

        Called from capture adapter (may be scapy thread or any other thread).
        Returns alert dict or None. Thread-safe.
        """
        ja4: str = fingerprint.get("ja4", "")
        if not ja4:
            return None

        alert: dict | None = None

        with self._lock:
            profile = self._profiles[src_ip]
            is_new = ja4 not in profile
            now = datetime.now(timezone.utc)

            # Update device profile
            if is_new:
                profile[ja4] = {"count": 1, "first_seen": now, "last_seen": now}
            else:
                profile[ja4]["count"] += 1
                profile[ja4]["last_seen"] = now

            unique_count = len(profile)

            if is_new:
                # NEW_TLS_FINGERPRINT fires exactly once per unique ja4 per src_ip
                alert = _make_alert(
                    alert_type="NEW_TLS_FINGERPRINT",
                    src_ip=src_ip,
                    dst_ip=dst_ip,
                    dst_port=dst_port,
                    fingerprint=fingerprint,
                    description=f"Новый TLS fingerprint у {src_ip} (всего уникальных: {unique_count})",
                    unique_count=unique_count,
                )

            # TOO_MANY check — with per-ip cooldown to avoid spam
            if unique_count > self._max_fps:
                last_alert = self._too_many_cooldown.get(src_ip)
                cooldown_expired = (
                    last_alert is None
                    or (now - last_alert).total_seconds() >= self._window
                )
                if cooldown_expired:
                    self._too_many_cooldown[src_ip] = now
                    alert = _make_alert(
                        alert_type="TOO_MANY_TLS_FINGERPRINTS",
                        src_ip=src_ip,
                        dst_ip=dst_ip,
                        dst_port=dst_port,
                        fingerprint=fingerprint,
                        description=(
                            f"Слишком много TLS fingerprints у {src_ip}: "
                            f"{unique_count} уникальных за {self._window}с"
                        ),
                        unique_count=unique_count,
                    )

        if alert is not None and self._alert_callback is not None:
            try:
                self._alert_callback(alert)
            except Exception:
                pass  # Never crash the capture thread

        return alert

    def get_profile(self, src_ip: str) -> dict:
        """Return TLS profile for a device (copy, thread-safe)."""
        with self._lock:
            return dict(self._profiles.get(src_ip, {}))

    def get_all_profiles(self) -> dict:
        """Return all device profiles (copy, thread-safe)."""
        with self._lock:
            return {ip: dict(fps) for ip, fps in self._profiles.items()}


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_alert(
    alert_type: str,
    src_ip: str,
    dst_ip: str,
    dst_port: int,
    fingerprint: dict,
    description: str,
    unique_count: int,
) -> dict:
    return {
        "type": alert_type,                # "NEW_TLS_FINGERPRINT" | "TOO_MANY_TLS_FINGERPRINTS"
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "dst_port": dst_port,
        "fingerprint": fingerprint,        # full fp dict: {ja4, sni, alpn, tls_version, ...}
        "description": description,
        "unique_count": unique_count,
    }
