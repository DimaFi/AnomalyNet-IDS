"""Unit tests for Windows ARP discovery backend.

All subprocess/scapy calls are mocked — no real network traffic.
"""
from __future__ import annotations

import sys
import types

import pytest

import app.discovery.backends.windows_arp as mod
from app.discovery.backends.windows_arp import (
    WindowsArpBackend,
    parse_arp_cache,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patch_hooks(monkeypatch, *, is_admin: bool, has_npcap: bool,
                 arp_a_rc: int = 0, arp_a_text: str = "") -> None:
    monkeypatch.setattr(mod, "_is_admin_fn", lambda: is_admin)
    monkeypatch.setattr(mod, "_has_npcap_fn", lambda: has_npcap)
    monkeypatch.setattr(mod, "_run_arp_a", lambda: (arp_a_rc, arp_a_text))


ARP_A_WINDOWS = """
Interface: 192.168.1.10 --- 0xe
  Internet Address      Physical Address      Type
  192.168.1.1           aa-bb-cc-dd-ee-01     dynamic
  192.168.1.50          aa-bb-cc-dd-ee-02     dynamic
  192.168.1.255         ff-ff-ff-ff-ff-ff     static
  224.0.0.22            01-00-5e-00-00-16     static
"""

ARP_A_LINUX = """
? (192.168.1.1) at aa:bb:cc:dd:ee:01 [ether] on eth0
? (192.168.1.50) at aa:bb:cc:dd:ee:02 [ether] on eth0
"""


# ── parse_arp_cache ───────────────────────────────────────────────────────────

class TestParseArpCache:
    def test_windows_format_two_hosts(self):
        pairs = parse_arp_cache(ARP_A_WINDOWS)
        ips = [p[0] for p in pairs]
        macs = [p[1] for p in pairs]
        assert "192.168.1.1" in ips
        assert "192.168.1.50" in ips
        # broadcast and multicast must be excluded
        assert "192.168.1.255" not in ips
        assert "224.0.0.22" not in ips

    def test_windows_mac_normalised_to_colon(self):
        pairs = parse_arp_cache(ARP_A_WINDOWS)
        macs = {p[1] for p in pairs}
        for mac in macs:
            assert "-" not in mac
            assert ":" in mac

    def test_linux_format(self):
        pairs = parse_arp_cache(ARP_A_LINUX)
        ips = [p[0] for p in pairs]
        assert "192.168.1.1" in ips
        assert "192.168.1.50" in ips

    def test_empty_string_returns_empty(self):
        assert parse_arp_cache("") == []

    def test_garbage_lines_skipped(self):
        text = "some random text\nno ip here\n\n"
        assert parse_arp_cache(text) == []

    def test_all_zeros_mac_excluded(self):
        text = "  192.168.1.99   00-00-00-00-00-00   dynamic"
        pairs = parse_arp_cache(text)
        assert pairs == []

    def test_broadcast_mac_excluded(self):
        text = "  192.168.1.99   ff-ff-ff-ff-ff-ff   static"
        pairs = parse_arp_cache(text)
        assert pairs == []


# ── WindowsArpBackend.source_tag ─────────────────────────────────────────────

class TestSourceTag:
    def test_no_admin_returns_arp_cache(self, monkeypatch):
        _patch_hooks(monkeypatch, is_admin=False, has_npcap=False)
        b = WindowsArpBackend()
        assert b.source_tag == "arp_cache"

    def test_admin_no_npcap_returns_arp_cache(self, monkeypatch):
        _patch_hooks(monkeypatch, is_admin=True, has_npcap=False)
        b = WindowsArpBackend()
        assert b.source_tag == "arp_cache"

    def test_admin_with_npcap_returns_npcap(self, monkeypatch):
        _patch_hooks(monkeypatch, is_admin=True, has_npcap=True)
        b = WindowsArpBackend()
        assert b.source_tag == "npcap"


# ── scan_network — arp cache fallback ────────────────────────────────────────

class TestScanNetworkArpCache:
    def test_no_admin_uses_arp_cache(self, monkeypatch):
        _patch_hooks(monkeypatch, is_admin=False, has_npcap=False,
                     arp_a_rc=0, arp_a_text=ARP_A_WINDOWS)
        b = WindowsArpBackend()
        devices = b.scan_network("192.168.1.0/24")
        ips = {d.ip for d in devices}
        assert "192.168.1.1" in ips
        assert "192.168.1.50" in ips

    def test_arp_cache_filters_to_network(self, monkeypatch):
        text = """
  10.0.0.1    aa-bb-cc-dd-ee-01   dynamic
  192.168.1.5 aa-bb-cc-dd-ee-02   dynamic
"""
        _patch_hooks(monkeypatch, is_admin=False, has_npcap=False,
                     arp_a_rc=0, arp_a_text=text)
        b = WindowsArpBackend()
        devices = b.scan_network("192.168.1.0/24")
        ips = {d.ip for d in devices}
        assert "192.168.1.5" in ips
        assert "10.0.0.1" not in ips

    def test_arp_a_failure_returns_empty(self, monkeypatch):
        _patch_hooks(monkeypatch, is_admin=False, has_npcap=False,
                     arp_a_rc=-1, arp_a_text="error")
        b = WindowsArpBackend()
        devices = b.scan_network("192.168.1.0/24")
        assert devices == []

    def test_device_fields_populated(self, monkeypatch):
        _patch_hooks(monkeypatch, is_admin=False, has_npcap=False,
                     arp_a_rc=0, arp_a_text=ARP_A_WINDOWS)
        b = WindowsArpBackend()
        devices = b.scan_network("192.168.1.0/24")
        assert all(d.mac for d in devices)
        assert all(d.ip for d in devices)
        assert all(d.is_online for d in devices)


# ── scan_network — Scapy path ─────────────────────────────────────────────────

class TestScanNetworkScapy:
    def _inject_scapy(self, monkeypatch, answered_hosts: list[tuple[str, str]]):
        """Inject fake scapy + srp that returns answered_hosts list of (ip, mac)."""
        class _FakeRcv:
            def __init__(self, ip, mac):
                self.psrc = ip
                self.hwsrc = mac

        class _FakeEther:
            def __truediv__(self, other): return self
            def __init__(self, **_): pass

        class _FakeARP:
            def __init__(self, **_): pass

        def _fake_srp(pkt, **kwargs):
            return [(None, _FakeRcv(ip, mac)) for ip, mac in answered_hosts], []

        # Inject scapy modules
        scapy_mod = types.ModuleType("scapy")
        scapy_layers = types.ModuleType("scapy.layers")
        scapy_l2 = types.ModuleType("scapy.layers.l2")
        scapy_l2.ARP = _FakeARP
        scapy_l2.Ether = _FakeEther
        scapy_sendrecv = types.ModuleType("scapy.sendrecv")
        scapy_sendrecv.srp = _fake_srp

        for name, m in [
            ("scapy", scapy_mod),
            ("scapy.layers", scapy_layers),
            ("scapy.layers.l2", scapy_l2),
            ("scapy.sendrecv", scapy_sendrecv),
        ]:
            monkeypatch.setitem(sys.modules, name, m)

    def test_scapy_returns_devices(self, monkeypatch):
        self._inject_scapy(monkeypatch, [("192.168.1.5", "AA:BB:CC:DD:EE:05")])
        _patch_hooks(monkeypatch, is_admin=True, has_npcap=True)
        b = WindowsArpBackend()
        devices = b.scan_network("192.168.1.0/24")
        assert len(devices) == 1
        assert devices[0].ip == "192.168.1.5"
        assert devices[0].mac == "AA:BB:CC:DD:EE:05"

    def test_scapy_exception_falls_back_to_arp_cache(self, monkeypatch):
        # Inject scapy that raises on srp
        class _FakeSrpRaise:
            pass
        scapy_mod = types.ModuleType("scapy")
        scapy_layers = types.ModuleType("scapy.layers")
        scapy_l2 = types.ModuleType("scapy.layers.l2")
        scapy_l2.ARP = object
        scapy_l2.Ether = object
        scapy_sendrecv = types.ModuleType("scapy.sendrecv")
        scapy_sendrecv.srp = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Npcap error"))
        for name, m in [
            ("scapy", scapy_mod), ("scapy.layers", scapy_layers),
            ("scapy.layers.l2", scapy_l2), ("scapy.sendrecv", scapy_sendrecv),
        ]:
            monkeypatch.setitem(sys.modules, name, m)

        _patch_hooks(monkeypatch, is_admin=True, has_npcap=True,
                     arp_a_rc=0, arp_a_text=ARP_A_WINDOWS)
        b = WindowsArpBackend()
        devices = b.scan_network("192.168.1.0/24")
        # Should fall back to arp cache
        assert len(devices) >= 2

    def test_scapy_import_error_falls_back_to_arp_cache(self, monkeypatch):
        # Remove scapy from sys.modules to simulate ImportError
        for key in list(sys.modules.keys()):
            if "scapy" in key:
                monkeypatch.delitem(sys.modules, key, raising=False)
        _patch_hooks(monkeypatch, is_admin=True, has_npcap=True,
                     arp_a_rc=0, arp_a_text=ARP_A_WINDOWS)
        b = WindowsArpBackend()
        devices = b.scan_network("192.168.1.0/24")
        # Falls back to arp cache gracefully
        assert isinstance(devices, list)


# ── scan_single ───────────────────────────────────────────────────────────────

class TestScanSingle:
    def test_no_admin_uses_arp_cache(self, monkeypatch):
        _patch_hooks(monkeypatch, is_admin=False, has_npcap=False,
                     arp_a_rc=0, arp_a_text=ARP_A_WINDOWS)
        b = WindowsArpBackend()
        mac = b.scan_single("192.168.1.1")
        assert mac is not None
        assert ":" in mac

    def test_not_in_cache_returns_none(self, monkeypatch):
        _patch_hooks(monkeypatch, is_admin=False, has_npcap=False,
                     arp_a_rc=0, arp_a_text=ARP_A_WINDOWS)
        b = WindowsArpBackend()
        mac = b.scan_single("10.99.99.99")
        assert mac is None

    def test_arp_failure_returns_none(self, monkeypatch):
        _patch_hooks(monkeypatch, is_admin=False, has_npcap=False,
                     arp_a_rc=-1, arp_a_text="")
        b = WindowsArpBackend()
        assert b.scan_single("192.168.1.1") is None
