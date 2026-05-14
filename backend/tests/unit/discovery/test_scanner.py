"""Unit tests for NetworkScanner platform-aware factory and scan_once."""
from __future__ import annotations

import platform
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import app.discovery.scanner as scanner_mod
from app.discovery.scanner import NetworkScanner, _create_arp_backend


# ── _create_arp_backend factory ───────────────────────────────────────────────

class TestCreateArpBackend:
    def test_linux_returns_linux_backend(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        from app.discovery.backends.linux_arp import LinuxArpBackend
        b = _create_arp_backend()
        assert isinstance(b, LinuxArpBackend)

    def test_windows_returns_windows_backend(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        from app.discovery.backends.windows_arp import WindowsArpBackend
        b = _create_arp_backend()
        assert isinstance(b, WindowsArpBackend)

    def test_other_os_returns_linux_backend(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        from app.discovery.backends.linux_arp import LinuxArpBackend
        b = _create_arp_backend()
        assert isinstance(b, LinuxArpBackend)


# ── NetworkScanner — scan_once delegates to backend ──────────────────────────

class TestNetworkScannerScanOnce:
    def _make_mock_backend(self, devices=None):
        b = MagicMock()
        b.source_tag = "mock"
        b.scan_network.return_value = devices or []
        return b

    def test_scan_once_empty_when_no_networks(self, monkeypatch):
        monkeypatch.setattr(scanner_mod, "detect_local_networks", lambda *a: [])
        monkeypatch.setattr(scanner_mod, "_create_arp_backend", lambda *a: self._make_mock_backend())
        s = NetworkScanner()
        result = s.scan_once()
        assert result == []

    def test_scan_once_calls_backend_scan_network(self, monkeypatch):
        from app.discovery.models import DeviceInfo
        from datetime import datetime
        fake_device = DeviceInfo(
            mac="AA:BB:CC:DD:EE:01", ip="192.168.1.5",
            first_seen=datetime.now(), last_seen=datetime.now(),
        )
        backend = self._make_mock_backend([fake_device])
        monkeypatch.setattr(scanner_mod, "detect_local_networks", lambda *a: ["192.168.1.0/24"])
        monkeypatch.setattr(scanner_mod, "_create_arp_backend", lambda *a: backend)
        s = NetworkScanner()
        result = s.scan_once()
        assert len(result) == 1
        assert result[0].ip == "192.168.1.5"

    def test_scan_once_catches_backend_exception(self, monkeypatch):
        backend = self._make_mock_backend()
        backend.scan_network.side_effect = RuntimeError("Scapy not available")
        monkeypatch.setattr(scanner_mod, "detect_local_networks", lambda *a: ["192.168.1.0/24"])
        monkeypatch.setattr(scanner_mod, "_create_arp_backend", lambda *a: backend)
        s = NetworkScanner()
        result = s.scan_once()
        assert result == []  # exception caught, returns empty

    def test_scan_once_aggregates_multiple_networks(self, monkeypatch):
        from app.discovery.models import DeviceInfo
        from datetime import datetime
        d1 = DeviceInfo(mac="AA:BB:CC:DD:EE:01", ip="192.168.1.1",
                        first_seen=datetime.now(), last_seen=datetime.now())
        d2 = DeviceInfo(mac="AA:BB:CC:DD:EE:02", ip="10.0.0.1",
                        first_seen=datetime.now(), last_seen=datetime.now())

        def _scan(net):
            return [d1] if "192" in net else [d2]

        backend = self._make_mock_backend()
        backend.scan_network.side_effect = _scan
        monkeypatch.setattr(scanner_mod, "detect_local_networks",
                            lambda *a: ["192.168.1.0/24", "10.0.0.0/24"])
        monkeypatch.setattr(scanner_mod, "_create_arp_backend", lambda *a: backend)
        s = NetworkScanner()
        result = s.scan_once()
        ips = {d.ip for d in result}
        assert ips == {"192.168.1.1", "10.0.0.1"}


# ── arp_single_ip backward compatibility ─────────────────────────────────────

class TestArpSingleIp:
    def test_delegates_to_backend(self, monkeypatch):
        backend = MagicMock()
        backend.source_tag = "mock"
        backend.scan_single.return_value = "AA:BB:CC:DD:EE:FF"
        monkeypatch.setattr(scanner_mod, "_create_arp_backend", lambda *a: backend)
        from app.discovery.scanner import arp_single_ip
        result = arp_single_ip("192.168.1.1")
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_returns_none_on_backend_none(self, monkeypatch):
        backend = MagicMock()
        backend.source_tag = "mock"
        backend.scan_single.return_value = None
        monkeypatch.setattr(scanner_mod, "_create_arp_backend", lambda *a: backend)
        from app.discovery.scanner import arp_single_ip
        assert arp_single_ip("10.0.0.1") is None


# ── Linux backend does not invoke windows_arp ─────────────────────────────────

class TestLinuxBackendNoWindowsDeps:
    def test_linux_backend_raises_on_missing_scapy(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        for key in list(sys.modules.keys()):
            if "scapy" in key:
                monkeypatch.delitem(sys.modules, key, raising=False)
        from app.discovery.backends.linux_arp import LinuxArpBackend
        b = LinuxArpBackend()
        with pytest.raises(RuntimeError, match="scapy is not installed"):
            b.scan_network("192.168.1.0/24")
