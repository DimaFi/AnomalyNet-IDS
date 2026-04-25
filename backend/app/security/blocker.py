"""
IP blocking abstraction — BaseFirewall / LinuxFirewall / MockFirewall.

LinuxFirewall uses two isolated iptables chains:
  ANOMALYNET_INPUT   — for PC mode   (jumps into INPUT)
  ANOMALYNET_FORWARD — for Gateway mode (jumps into FORWARD)

All blocking rules live in the dedicated chain; system chains are only
touched for the single -j ANOMALYNET_* jump rule.

Usage:
    fw = create_firewall(mode="pc")
    fw.block_ip("192.168.1.100", whitelist={"192.168.1.1"})
    fw.snapshot()           # save iptables state before changes
    fw.restore("/path/to/backup")
    fw.flush()              # remove all ANOMALYNET rules
"""

from __future__ import annotations

import logging
import platform
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

_log = logging.getLogger("app.security.blocker")


# ── injectable run_command (replaced in tests) ────────────────────────────────

def _default_run(cmd: list[str]) -> tuple[int, str]:
    """Run cmd, return (returncode, stderr_text)."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        return result.returncode, result.stderr.decode(errors="replace").strip()
    except FileNotFoundError:
        return -1, "command not found"
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as exc:
        return -1, str(exc)


# Module-level hook — replace in tests via monkeypatch
run_command: Callable[[list[str]], tuple[int, str]] = _default_run


# ── Chain names ───────────────────────────────────────────────────────────────

_CHAIN_INPUT   = "ANOMALYNET_INPUT"
_CHAIN_FORWARD = "ANOMALYNET_FORWARD"


# ── Abstract base ─────────────────────────────────────────────────────────────

class BaseFirewall(ABC):
    def __init__(self, blocking_mode: str = "pc") -> None:
        self.blocking_mode = blocking_mode  # "pc" | "gateway"

    @abstractmethod
    def block_ip(self, ip: str, whitelist: set[str] | None = None) -> bool:
        """Block IP. Returns True on success, False if rejected or failed."""

    @abstractmethod
    def unblock_ip(self, ip: str) -> bool:
        """Remove block for IP. Returns True on success."""

    @abstractmethod
    def list_rules(self) -> list[str]:
        """Return list of currently blocked IPs from the active chain."""

    @abstractmethod
    def flush(self) -> None:
        """Remove all rules from the active chain."""

    @abstractmethod
    def snapshot(self, path: str) -> bool:
        """Save current iptables state to file. Returns True on success."""

    @abstractmethod
    def restore(self, path: str) -> bool:
        """Restore iptables state from file. Returns True on success."""

    def sync_rules(self, ips: list[str], whitelist: set[str] | None = None) -> int:
        """
        Ensure all IPs in `ips` are present in the active chain.
        Skips IPs that are already blocked (no duplicates).
        Skips protected / whitelisted IPs.
        Returns the number of rules actually added.
        """
        existing = set(self.list_rules())
        added = 0
        for ip in ips:
            if ip in existing:
                continue
            if self.block_ip(ip, whitelist):
                added += 1
        if added:
            _log.info("[SYNC] restored %d rule(s) from registry", added)
        return added

    def get_warnings(self) -> list[str]:
        return []


# ── Linux implementation ──────────────────────────────────────────────────────

def _collect_local_ips() -> set[str]:
    """Collect all local interface IPs using psutil (best-effort)."""
    ips: set[str] = {"127.0.0.1"}
    try:
        import psutil  # type: ignore[import]
        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if a.family == 2:  # AF_INET
                    ips.add(a.address)
    except Exception:
        pass
    return ips


def _get_default_gateway() -> str | None:
    """Parse default gateway from `ip route show default`."""
    code, _ = run_command(["ip", "route", "show", "default"])
    if code != 0:
        return None
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=5,
        )
        for token, nxt in zip(result.stdout.split(), result.stdout.split()[1:]):
            if token == "via":
                return nxt
    except Exception:
        pass
    return None


class LinuxFirewall(BaseFirewall):
    def __init__(self, blocking_mode: str = "pc") -> None:
        super().__init__(blocking_mode)
        self._chain = _CHAIN_INPUT if blocking_mode == "pc" else _CHAIN_FORWARD
        self._parent_chain = "INPUT" if blocking_mode == "pc" else "FORWARD"
        self._chain_ready = False
        self._snapshot_done = False
        # Build fail-safe set once at init (best-effort)
        self._protected: set[str] = _collect_local_ips()
        gw = _get_default_gateway()
        if gw:
            self._protected.add(gw)

    # ── internal helpers ──────────────────────────────────────────────────────

    def _ensure_chain(self) -> None:
        if self._chain_ready:
            return
        # Create chain if it doesn't exist
        code, _ = run_command(["iptables", "-L", self._chain, "-n"])
        if code != 0:
            rc, err = run_command(["iptables", "-N", self._chain])
            if rc != 0:
                _log.error("Failed to create chain %s: %s", self._chain, err)
                return
        # Insert jump into parent chain (idempotent: ignore error if rule exists)
        run_command(["iptables", "-I", self._parent_chain, "-j", self._chain])
        self._chain_ready = True
        _log.info("[CHAIN] %s ready (mode=%s)", self._chain, self.blocking_mode)

    def _maybe_snapshot(self, snapshot_path: str) -> None:
        if self._snapshot_done:
            return
        ok = self.snapshot(snapshot_path)
        if ok:
            self._snapshot_done = True

    # ── public interface ──────────────────────────────────────────────────────

    def block_ip(self, ip: str, whitelist: set[str] | None = None) -> bool:
        combined = self._protected | (whitelist or set())
        if ip in combined:
            _log.warning("[FAIL-SAFE] attempt to block protected IP %s — rejected", ip)
            return False
        self._ensure_chain()
        rc, err = run_command(["iptables", "-A", self._chain, "-s", ip, "-j", "DROP"])
        if rc == 0:
            _log.info("[BLOCK] %s → chain %s (%s mode)", ip, self._chain, self.blocking_mode)
            return True
        _log.error("[ERROR] block_ip %s failed (rc=%d): %s", ip, rc, err)
        return False

    def unblock_ip(self, ip: str) -> bool:
        rc, err = run_command(["iptables", "-D", self._chain, "-s", ip, "-j", "DROP"])
        if rc == 0:
            _log.info("[UNBLOCK] %s", ip)
            return True
        _log.error("[ERROR] unblock_ip %s failed (rc=%d): %s", ip, rc, err)
        return False

    def list_rules(self) -> list[str]:
        try:
            result = subprocess.run(
                ["iptables", "-L", self._chain, "-n", "--line-numbers"],
                capture_output=True, text=True, timeout=10,
            )
            ips = []
            for line in result.stdout.splitlines():
                parts = line.split()
                # Format: num DROP all -- source destination
                if len(parts) >= 5 and parts[1] == "DROP":
                    ips.append(parts[3])
            return ips
        except Exception:
            return []

    def flush(self) -> None:
        rc, err = run_command(["iptables", "-F", self._chain])
        if rc == 0:
            _log.info("[FLUSH] chain %s cleared", self._chain)
        else:
            _log.error("[ERROR] flush %s failed (rc=%d): %s", self._chain, rc, err)
        self._chain_ready = False

    def snapshot(self, path: str) -> bool:
        dest = Path(path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["iptables-save"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                dest.write_bytes(result.stdout)
                _log.info("[SNAPSHOT] saved to %s", path)
                return True
            _log.error("[SNAPSHOT] iptables-save failed: %s", result.stderr.decode(errors="replace"))
            return False
        except Exception as exc:
            _log.error("[SNAPSHOT] exception: %s", exc)
            return False

    def restore(self, path: str) -> bool:
        src = Path(path)
        if not src.exists():
            _log.warning("[RESTORE] backup file not found: %s", path)
            return False
        try:
            with src.open("rb") as f:
                result = subprocess.run(
                    ["iptables-restore"],
                    stdin=f, capture_output=True, timeout=10,
                )
            if result.returncode == 0:
                _log.info("[RESTORE] iptables-restore from %s — OK", path)
                self._chain_ready = False
                self._snapshot_done = False
                return True
            _log.error("[RESTORE] iptables-restore failed: %s", result.stderr.decode(errors="replace"))
            return False
        except Exception as exc:
            _log.error("[RESTORE] exception: %s", exc)
            return False


# ── Mock implementation (Windows / tests) ────────────────────────────────────

class MockFirewall(BaseFirewall):
    """In-memory firewall — no system calls. For Windows and unit tests."""

    def __init__(self, blocking_mode: str = "pc") -> None:
        super().__init__(blocking_mode)
        self._blocked: set[str] = set()

    def block_ip(self, ip: str, whitelist: set[str] | None = None) -> bool:
        if whitelist and ip in whitelist:
            return False
        self._blocked.add(ip)
        _log.info("[MOCK BLOCK] %s", ip)
        return True

    def unblock_ip(self, ip: str) -> bool:
        self._blocked.discard(ip)
        _log.info("[MOCK UNBLOCK] %s", ip)
        return True

    def list_rules(self) -> list[str]:
        return list(self._blocked)

    def flush(self) -> None:
        self._blocked.clear()
        _log.info("[MOCK FLUSH]")

    def snapshot(self, path: str) -> bool:
        _log.info("[MOCK SNAPSHOT] (no-op) path=%s", path)
        return True

    def restore(self, path: str) -> bool:
        _log.info("[MOCK RESTORE] (no-op) path=%s", path)
        return True

    def get_warnings(self) -> list[str]:
        return ["MockFirewall active — iptables not used (non-Linux platform or test mode)"]


# ── Factory ───────────────────────────────────────────────────────────────────

def create_firewall(mode: str = "pc") -> BaseFirewall:
    """
    Returns the appropriate firewall implementation for the current platform.
    Add `elif platform.system() == "Windows": return WindowsFirewall(mode)`
    here when WindowsFirewall is implemented — service.py does not need changes.
    """
    if platform.system() == "Linux":
        return LinuxFirewall(blocking_mode=mode)
    return MockFirewall(blocking_mode=mode)
