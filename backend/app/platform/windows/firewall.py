"""
Windows firewall backend using netsh advfirewall.

Phase 3: WindowsNetshFirewall blocks inbound traffic per-IP using
named Windows Firewall rules (ANOMALYNET_BLOCK_<IP>).

Requires Administrator privileges.
Without elevation, create_windows_firewall() falls back to MockFirewall.

All rules are inbound-only (PC mode). Gateway/FORWARD mode is Phase 2.1.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable

from app.security.blocker import BaseFirewall, MockFirewall

_log = logging.getLogger("app.security.windows_firewall")

# Prefix shared by all AnomalyNet blocking rules
_RULE_PREFIX = "ANOMALYNET_BLOCK_"


# ── injectable run hook (replaced in tests via monkeypatch) ──────────────────

def _default_run_netsh(cmd: list[str]) -> tuple[int, str]:
    """Run a netsh command. Returns (returncode, stdout+stderr text)."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        out = result.stdout.decode(errors="replace")
        err = result.stderr.decode(errors="replace").strip()
        text = (out + "\n" + err).strip() if err else out.rstrip()
        return result.returncode, text
    except FileNotFoundError:
        return -1, "netsh not found"
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as exc:
        return -1, str(exc)


run_netsh: Callable[[list[str]], tuple[int, str]] = _default_run_netsh


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_admin() -> bool:
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
    except Exception:
        return False


def _collect_protected_ips() -> set[str]:
    """Build the set of IPs that must never be blocked (loopback, local, gateway)."""
    protected: set[str] = {"127.0.0.1", "::1", "0.0.0.0"}
    # Local interface IPs via psutil
    try:
        import psutil  # type: ignore[import]
        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if a.family in (2, 23):  # AF_INET=2, AF_INET6=23 on Windows
                    protected.add(a.address.split("%")[0])  # strip IPv6 scope ID
    except Exception:
        pass
    # Default gateway(s) from routing table
    try:
        result = subprocess.run(
            ["route", "print", "0.0.0.0"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            # IPv4 default route columns: Network  Mask  Gateway  Interface  Metric
            if len(parts) >= 3 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                protected.add(parts[2])
    except Exception:
        pass
    return protected


# ── Windows Firewall implementation ──────────────────────────────────────────

class WindowsNetshFirewall(BaseFirewall):
    """
    Blocks IPs by adding named inbound rules to Windows Firewall via netsh.

    Rule naming: ANOMALYNET_BLOCK_<ip>
    Example: ANOMALYNET_BLOCK_192.168.1.100

    Requires Administrator privileges (verified by the factory, not here).
    """

    def __init__(self, blocking_mode: str = "pc") -> None:
        super().__init__(blocking_mode)
        self._protected: set[str] = _collect_protected_ips()

    @staticmethod
    def _rule_name(ip: str) -> str:
        return f"{_RULE_PREFIX}{ip}"

    def block_ip(self, ip: str, whitelist: set[str] | None = None) -> bool:
        combined = self._protected | (whitelist or set())
        if ip in combined:
            _log.warning("[FAIL-SAFE] attempt to block protected IP %s — rejected", ip)
            return False
        rule = self._rule_name(ip)
        rc, out = run_netsh([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule}",
            "dir=in",
            "action=block",
            f"remoteip={ip}",
            "enable=yes",
            "profile=any",
        ])
        if rc == 0:
            _log.info("[BLOCK] %s → Windows Firewall rule %r", ip, rule)
            return True
        _log.error("[ERROR] block_ip %s failed (rc=%d): %s", ip, rc, out)
        return False

    def unblock_ip(self, ip: str) -> bool:
        rule = self._rule_name(ip)
        rc, out = run_netsh([
            "netsh", "advfirewall", "firewall", "delete", "rule",
            f"name={rule}",
        ])
        if rc == 0:
            _log.info("[UNBLOCK] %s (rule %r deleted)", ip, rule)
            return True
        _log.error("[ERROR] unblock_ip %s failed (rc=%d): %s", ip, rc, out)
        return False

    def is_blocked(self, ip: str) -> bool:
        """Check whether a specific IP has an active ANOMALYNET block rule."""
        rule = self._rule_name(ip)
        rc, _ = run_netsh([
            "netsh", "advfirewall", "firewall", "show", "rule",
            f"name={rule}",
        ])
        return rc == 0

    def list_rules(self) -> list[str]:
        """Return IPs with active ANOMALYNET_BLOCK_ rules, parsed from netsh output."""
        rc, text = run_netsh([
            "netsh", "advfirewall", "firewall", "show", "rule", "name=all",
        ])
        # rc=1 means "No rules match" — that is fine (empty list)
        # rc=-1 means netsh unavailable — also return empty
        ips: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("Rule Name:"):
                name = stripped.split(":", 1)[1].strip()
                if name.startswith(_RULE_PREFIX):
                    ips.append(name[len(_RULE_PREFIX):])
        return ips

    def list_blocked(self) -> list[str]:
        return self.list_rules()

    def flush(self) -> None:
        """Remove all ANOMALYNET_BLOCK_* rules from Windows Firewall."""
        rules = self.list_rules()
        removed = 0
        for ip in rules:
            rule = self._rule_name(ip)
            rc, _ = run_netsh([
                "netsh", "advfirewall", "firewall", "delete", "rule",
                f"name={rule}",
            ])
            if rc == 0:
                removed += 1
        _log.info("[FLUSH] removed %d ANOMALYNET rule(s)", removed)

    def snapshot(self, path: str) -> bool:
        """Export Windows Firewall policy to .wfw file via netsh advfirewall export."""
        dest = Path(path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            _log.error("[SNAPSHOT] cannot create directory: %s", exc)
            return False
        rc, out = run_netsh([
            "netsh", "advfirewall", "export",
            str(dest.resolve()),
        ])
        if rc == 0:
            _log.info("[SNAPSHOT] Windows Firewall exported to %s", path)
            return True
        _log.error("[SNAPSHOT] netsh export failed (rc=%d): %s", rc, out)
        return False

    def restore(self, path: str) -> bool:
        """Import Windows Firewall policy from .wfw file via netsh advfirewall import."""
        src = Path(path)
        if not src.exists():
            _log.warning("[RESTORE] backup file not found: %s", path)
            return False
        rc, out = run_netsh([
            "netsh", "advfirewall", "import",
            str(src.resolve()),
        ])
        if rc == 0:
            _log.info("[RESTORE] Windows Firewall restored from %s", path)
            return True
        _log.error("[RESTORE] netsh import failed (rc=%d): %s", rc, out)
        return False

    def get_warnings(self) -> list[str]:
        return []


# ── Factory ───────────────────────────────────────────────────────────────────

def create_windows_firewall(mode: str = "pc") -> BaseFirewall:
    """
    Returns WindowsNetshFirewall when running as Administrator,
    MockFirewall otherwise (no actual IP blocking, warning logged).
    """
    if _is_admin():
        _log.info("[FIREWALL] Administrator detected — using WindowsNetshFirewall")
        return WindowsNetshFirewall(blocking_mode=mode)
    _log.warning(
        "[FIREWALL] Not running as Administrator — "
        "falling back to MockFirewall. Restart as Administrator to enable real blocking."
    )
    return MockFirewall(blocking_mode=mode)
