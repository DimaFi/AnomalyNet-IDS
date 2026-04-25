from __future__ import annotations

import math
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Callable


class DnsMonitor:
    """Thread-safe passive DNS monitor.

    Called from the scapy capture thread via on_dns_packet().
    Uses threading.Lock for all mutable state.

    Alert callback:
        set_alert_callback(fn) registers a callable invoked synchronously
        (still in the scapy thread) whenever a DGA or tunneling alert fires.
        fn receives the alert dict; exceptions are silently swallowed so a
        broken callback never crashes the capture loop.
    """

    def __init__(
        self,
        max_recent: int = 1000,
        max_per_device: int = 200,
        max_alerts: int = 200,
    ) -> None:
        self._lock = threading.Lock()
        self._all_recent: deque[dict] = deque(maxlen=max_recent)
        self._per_device: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=max_per_device))
        self._alerts: deque[dict] = deque(maxlen=max_alerts)
        self._domain_counts: dict[str, int] = defaultdict(int)
        self._device_domain_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._alert_callback: Callable[[dict], None] | None = None

    def set_alert_callback(self, callback: Callable[[dict], None]) -> None:
        """Register a callable to be invoked on every detected alert."""
        self._alert_callback = callback

    # ── Public API ────────────────────────────────────────────────────────────

    def on_dns_packet(self, src_ip: str, domain: str, qtype: str) -> dict | None:
        """Record a DNS query and return an anomaly dict if detected, else None."""
        ts = datetime.now(timezone.utc).isoformat()
        alert = self._check(src_ip, domain)
        entry: dict = {
            "ts": ts,
            "domain": domain,
            "qtype": qtype,
            "src_ip": src_ip,
            "alert_type": alert["type"] if alert else None,
            "entropy": alert.get("entropy") if alert else None,
        }
        with self._lock:
            self._all_recent.appendleft(entry)
            self._per_device[src_ip].appendleft(entry)
            self._domain_counts[domain] += 1
            self._device_domain_counts[src_ip][domain] += 1
            if alert:
                self._alerts.appendleft({**alert, "ts": ts})
        if alert and self._alert_callback is not None:
            try:
                self._alert_callback(alert)
            except Exception:
                pass
        return alert

    def get_recent(self, src_ip: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            if src_ip:
                return list(self._per_device.get(src_ip, []))[:limit]
            return list(self._all_recent)[:limit]

    def get_top_domains(self, src_ip: str | None = None, limit: int = 20) -> list[dict]:
        with self._lock:
            counts: dict[str, int] = (
                dict(self._device_domain_counts.get(src_ip, {}))
                if src_ip
                else dict(self._domain_counts)
            )
        return [
            {"domain": d, "count": c}
            for d, c in sorted(counts.items(), key=lambda x: -x[1])[:limit]
        ]

    def get_alerts(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._alerts)[:limit]

    def get_device_summary(self, src_ip: str) -> dict:
        with self._lock:
            counts = dict(self._device_domain_counts.get(src_ip, {}))
            top5 = sorted(counts.items(), key=lambda x: -x[1])[:5]
            alert_count = sum(1 for a in self._alerts if a.get("src_ip") == src_ip)
        return {
            "total_queries": sum(counts.values()),
            "alert_count": alert_count,
            "top_domains": [{"domain": d, "count": c} for d, c in top5],
        }

    # ── Detection logic ───────────────────────────────────────────────────────

    @staticmethod
    def _entropy(s: str) -> float:
        """Shannon entropy — high for DGA-generated labels."""
        if not s:
            return 0.0
        freq: dict[str, int] = {}
        for c in s:
            freq[c] = freq.get(c, 0) + 1
        return -sum((v / len(s)) * math.log2(v / len(s)) for v in freq.values())

    def _check(self, src_ip: str, domain: str) -> dict | None:
        label = domain.split(".")[0]
        ent = self._entropy(label)

        # DGA heuristic: high entropy + random-looking character mix (digits present).
        # Threshold 4.0 + digit_ratio >= 15% avoids FP on long human-readable names
        # like "firebaseremoteconfig". Frontend filters (.local, PTR, etc.) are the
        # user-configurable layer on top — nothing is hidden here.
        digit_ratio = sum(1 for c in label if c.isdigit()) / max(len(label), 1)
        if ent > 4.0 and len(label) > 8 and digit_ratio >= 0.15:
            return {
                "type": "DGA_DOMAIN",
                "domain": domain,
                "src_ip": src_ip,
                "entropy": round(ent, 2),
                "description": f"Возможный DGA домен: энтропия {ent:.2f}, цифры {digit_ratio:.0%}",
            }

        # DNS tunneling: abnormally long label (data exfiltration via subdomains)
        if len(label) > 50:
            return {
                "type": "DNS_TUNNELING",
                "domain": (domain[:80] + "…") if len(domain) > 80 else domain,
                "src_ip": src_ip,
                "entropy": None,
                "description": "Подозрение на DNS tunneling: аномально длинный запрос",
            }

        return None
