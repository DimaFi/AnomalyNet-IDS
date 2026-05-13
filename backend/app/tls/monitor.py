"""
Platform-independent TLS behavioral monitor.

Accepts already-parsed fingerprint dicts (not raw packets).
Thread-safe — called from scapy capture thread.

Alert types
-----------
NEW_TLS_FINGERPRINT       first time this src_ip uses a particular JA4
TOO_MANY_TLS_FINGERPRINTS src_ip has rotated through >max_fps unique JA4s
                           in the configured window (possible TLS scanning / malware)
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

_log = logging.getLogger("app.tls.monitor")


# ── Stats ─────────────────────────────────────────────────────────────────────

@dataclass
class TLSMonitorStats:
    fingerprints_seen:     int = 0   # total on_fingerprint calls
    alerts_new:            int = 0   # NEW_TLS_FINGERPRINT emitted
    alerts_too_many:       int = 0   # TOO_MANY_TLS_FINGERPRINTS emitted
    ips_tracked:           int = 0   # current unique IPs in profiles
    profiles_total:        int = 0   # current total unique fingerprints stored
    cooldown_entries:      int = 0   # current _too_many_cooldown entries
    profile_expirations:   int = 0   # fingerprint entries removed by window


# ── Monitor ───────────────────────────────────────────────────────────────────

class TLSMonitor:
    """Platform-independent TLS behavioral monitor.

    Parameters
    ----------
    max_fingerprints_per_ip
        How many unique JA4 fingerprints a single src_ip may have in the window
        before a TOO_MANY alert fires.
    profile_window_seconds
        How long a fingerprint entry stays in the profile.  After expiry the
        same JA4 from the same IP is treated as *new* again.
    too_many_cooldown_seconds
        Minimum time between consecutive TOO_MANY alerts for the same src_ip.
    window_seconds
        Deprecated alias — sets both profile_window_seconds AND
        too_many_cooldown_seconds for backward compatibility.
    """

    def __init__(
        self,
        max_fingerprints_per_ip: int = 8,
        profile_window_seconds:  int = 60,
        too_many_cooldown_seconds: int = 60,
        window_seconds: int | None = None,   # legacy compat
    ) -> None:
        if window_seconds is not None:
            profile_window_seconds    = window_seconds
            too_many_cooldown_seconds = window_seconds

        self._max_fps         = max_fingerprints_per_ip
        self._profile_window  = max(profile_window_seconds, 0)
        self._cooldown        = max(too_many_cooldown_seconds, 0)

        self._lock = threading.Lock()

        # ip → {ja4_key → {"count": int, "first_seen": datetime, "last_seen": datetime}}
        self._profiles: dict[str, dict[str, dict]] = defaultdict(dict)

        # ip → datetime of last TOO_MANY alert (for cooldown logic)
        # NOTE: purged together with _profiles to prevent unbounded growth
        self._too_many_cooldown: dict[str, datetime] = {}

        self._alert_callback: Callable[[dict], None] | None = None
        self._stats = TLSMonitorStats()

    # ── public ───────────────────────────────────────────────────────────────

    def set_alert_callback(self, callback: Callable[[dict], None]) -> None:
        """Register callable invoked synchronously on every alert.

        Must be fast and exception-safe — runs inside the capture thread.
        """
        self._alert_callback = callback

    def on_fingerprint(
        self,
        src_ip:      str,
        dst_ip:      str,
        dst_port:    int,
        fingerprint: dict,
    ) -> dict | None:
        """Process one TLS ClientHello fingerprint.

        Returns alert dict if an alert was generated, else None.
        Thread-safe — may be called from any thread.
        """
        # Prefer canonical ja4; fall back to legacy for older stored events
        key = fingerprint.get("ja4") or fingerprint.get("ja4_legacy") or ""
        if not key:
            return None

        alert: dict | None = None

        with self._lock:
            now = datetime.now(timezone.utc)
            self._stats.fingerprints_seen += 1

            # Expire stale entries for this IP before making decisions
            self._expire_for_ip(src_ip, now)

            profile   = self._profiles[src_ip]
            is_new    = key not in profile

            if is_new:
                profile[key] = {"count": 1, "first_seen": now, "last_seen": now,
                                "fingerprint": dict(fingerprint)}
            else:
                profile[key]["count"] += 1
                profile[key]["last_seen"] = now

            unique_count = len(profile)

            if is_new:
                self._stats.alerts_new += 1
                alert = _make_alert(
                    alert_type="NEW_TLS_FINGERPRINT",
                    src_ip=src_ip, dst_ip=dst_ip, dst_port=dst_port,
                    fingerprint=fingerprint,
                    description=f"Новый TLS fingerprint у {src_ip} (всего уникальных: {unique_count})",
                    unique_count=unique_count,
                )

            # TOO_MANY — with cooldown per src_ip
            if unique_count > self._max_fps:
                last = self._too_many_cooldown.get(src_ip)
                if last is None or (now - last).total_seconds() >= self._cooldown:
                    self._too_many_cooldown[src_ip] = now
                    self._stats.alerts_too_many += 1
                    alert = _make_alert(
                        alert_type="TOO_MANY_TLS_FINGERPRINTS",
                        src_ip=src_ip, dst_ip=dst_ip, dst_port=dst_port,
                        fingerprint=fingerprint,
                        description=(
                            f"Слишком много TLS fingerprints у {src_ip}: "
                            f"{unique_count} уникальных за {self._profile_window}с"
                        ),
                        unique_count=unique_count,
                    )

            # Keep stats in sync
            self._stats.ips_tracked    = len(self._profiles)
            self._stats.profiles_total = sum(len(v) for v in self._profiles.values())
            self._stats.cooldown_entries = len(self._too_many_cooldown)

        if alert is not None and self._alert_callback is not None:
            try:
                self._alert_callback(alert)
            except Exception:
                pass  # never crash capture thread

        return alert

    # ── profile accessors ────────────────────────────────────────────────────

    def get_profile(self, src_ip: str) -> dict:
        """Return profile for one IP (copy, thread-safe)."""
        with self._lock:
            now = datetime.now(timezone.utc)
            self._expire_for_ip(src_ip, now)
            return dict(self._profiles.get(src_ip, {}))

    def get_all_profiles(self) -> dict:
        """Return all profiles (copy, thread-safe)."""
        with self._lock:
            now = datetime.now(timezone.utc)
            self._expire_all(now)
            return {ip: dict(fps) for ip, fps in self._profiles.items()}

    def get_stats(self) -> dict:
        """Return a snapshot of monitor statistics (thread-safe)."""
        with self._lock:
            s = self._stats
            return {
                "fingerprints_seen":   s.fingerprints_seen,
                "alerts_new":          s.alerts_new,
                "alerts_too_many":     s.alerts_too_many,
                "ips_tracked":         s.ips_tracked,
                "profiles_total":      s.profiles_total,
                "cooldown_entries":    s.cooldown_entries,
                "profile_expirations": s.profile_expirations,
            }

    # ── internal helpers ─────────────────────────────────────────────────────

    def _expire_for_ip(self, src_ip: str, now: datetime) -> None:
        """Expire stale fingerprint entries for one IP and purge cooldown."""
        if self._profile_window <= 0:
            # window=0 → expire immediately (useful for tests)
            removed = len(self._profiles.get(src_ip, {}))
            self._profiles.pop(src_ip, None)
            self._stats.profile_expirations += removed
            # Purge cooldown for IPs with no active profile
            self._too_many_cooldown.pop(src_ip, None)
            return

        cutoff  = now - timedelta(seconds=self._profile_window)
        profile = self._profiles.get(src_ip)
        if not profile:
            return

        stale = [k for k, v in profile.items() if v["last_seen"] <= cutoff]
        for k in stale:
            profile.pop(k)
            self._stats.profile_expirations += 1

        if not profile:
            self._profiles.pop(src_ip, None)
            # Purge cooldown entry too — prevents unbounded growth
            self._too_many_cooldown.pop(src_ip, None)

    def _expire_all(self, now: datetime) -> None:
        """Expire stale entries for all IPs (called on get_all_profiles)."""
        for ip in list(self._profiles):
            self._expire_for_ip(ip, now)


# ── Alert factory ─────────────────────────────────────────────────────────────

def _make_alert(
    alert_type:  str,
    src_ip:      str,
    dst_ip:      str,
    dst_port:    int,
    fingerprint: dict,
    description: str,
    unique_count: int,
) -> dict:
    return {
        "type":         alert_type,
        "src_ip":       src_ip,
        "dst_ip":       dst_ip,
        "dst_port":     dst_port,
        "fingerprint":  fingerprint,
        "description":  description,
        "unique_count": unique_count,
    }
