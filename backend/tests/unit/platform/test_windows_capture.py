"""
Unit tests for WindowsNpcapCapture — all subprocess/scapy calls are mocked.

Tests run on Linux CI and Windows dev machines alike:
every test patches the OS/Scapy boundary so no Npcap or admin rights needed.
"""

from __future__ import annotations

import sys
import types
import pytest
from unittest.mock import patch, MagicMock


def _inject_scapy_mock(monkeypatch, if_list: list | None = None, raise_import: bool = False):
    """Inject a fake scapy.arch.windows into sys.modules so patch() works."""
    fake_scapy = types.ModuleType("scapy")
    fake_arch = types.ModuleType("scapy.arch")
    fake_windows = types.ModuleType("scapy.arch.windows")

    if raise_import:
        def _get_windows_if_list():
            raise ImportError("mocked — no scapy")
    else:
        def _get_windows_if_list():
            return if_list if if_list is not None else []

    fake_windows.get_windows_if_list = _get_windows_if_list
    fake_arch.windows = fake_windows

    monkeypatch.setitem(sys.modules, "scapy", fake_scapy)
    monkeypatch.setitem(sys.modules, "scapy.arch", fake_arch)
    monkeypatch.setitem(sys.modules, "scapy.arch.windows", fake_windows)
    return fake_windows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_capture(interfaces=None, detection_mode="simple"):
    from app.capture.adapters.windows.npcap_adapter import WindowsNpcapCapture
    ifaces = interfaces if interfaces is not None else ["Ethernet"]
    return WindowsNpcapCapture(interfaces=ifaces, detection_mode=detection_mode)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------

class TestWindowsNpcapCaptureInstantiation:
    def test_mode_attribute(self):
        from app.capture.adapters.windows.npcap_adapter import WindowsNpcapCapture
        assert WindowsNpcapCapture.mode == "windows_live"

    def test_name_attribute(self):
        from app.capture.adapters.windows.npcap_adapter import WindowsNpcapCapture
        assert "Windows" in WindowsNpcapCapture.name

    def test_default_interface_stored(self):
        cap = _make_capture(["Ethernet"])
        assert cap._interfaces == ["Ethernet"]

    def test_string_interface_wrapped_in_list(self):
        from app.capture.adapters.windows.npcap_adapter import WindowsNpcapCapture
        cap = WindowsNpcapCapture(interfaces="Wi-Fi")
        assert cap._interfaces == ["Wi-Fi"]

    def test_multi_interface_stored(self):
        cap = _make_capture(["Ethernet", "Wi-Fi"])
        assert len(cap._interfaces) == 2

    def test_initial_tls_stats_zero(self):
        cap = _make_capture()
        stats = cap.get_tls_stats()
        assert all(v == 0 for v in stats.values())

    def test_dns_monitor_initially_none(self):
        cap = _make_capture()
        assert cap._dns_monitor is None

    def test_tls_monitor_initially_none(self):
        cap = _make_capture()
        assert cap._tls_monitor is None

    def test_set_dns_monitor(self):
        cap = _make_capture()
        mock_dns = MagicMock()
        cap.set_dns_monitor(mock_dns)
        assert cap._dns_monitor is mock_dns

    def test_set_tls_monitor(self):
        cap = _make_capture()
        mock_tls = MagicMock()
        cap.set_tls_monitor(mock_tls)
        assert cap._tls_monitor is mock_tls


# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

class TestStartPrerequisites:
    def test_start_raises_without_admin(self):
        import asyncio
        cap = _make_capture()
        with patch("app.capture.adapters.windows.npcap_adapter._check_admin", return_value=False):
            with pytest.raises(RuntimeError, match="Administrator"):
                asyncio.run(cap.start())

    def test_start_raises_without_npcap(self):
        import asyncio
        cap = _make_capture()
        with (
            patch("app.capture.adapters.windows.npcap_adapter._check_admin", return_value=True),
            patch("app.capture.adapters.windows.npcap_adapter._check_npcap_available", return_value=False),
        ):
            with pytest.raises(RuntimeError, match="[Nn]pcap"):
                asyncio.run(cap.start())


# ---------------------------------------------------------------------------
# Interface resolution
# ---------------------------------------------------------------------------

class TestResolveInterface:
    def test_guid_notation_unchanged(self):
        from app.capture.adapters.windows.npcap_adapter import _resolve_interface
        guid = "{1A2B3C4D-CAFE-DEAD-BEEF-000000000001}"
        assert _resolve_interface(guid) == guid

    def test_npf_notation_unchanged(self):
        from app.capture.adapters.windows.npcap_adapter import _resolve_interface
        npf = "\\Device\\NPF_{1A2B3C4D-CAFE-DEAD-BEEF-000000000001}"
        assert _resolve_interface(npf) == npf

    def test_name_resolved_to_guid(self, monkeypatch):
        fake_ifaces = [
            {"name": "Ethernet", "description": "Intel(R) Ethernet", "guid": "AABBCCDD-1111-2222-3333-AABBCCDDEEFF"},
            {"name": "Wi-Fi", "description": "Wi-Fi Adapter", "guid": "11223344-AAAA-BBBB-CCCC-112233445566"},
        ]
        _inject_scapy_mock(monkeypatch, if_list=fake_ifaces)
        from app.capture.adapters.windows.npcap_adapter import _resolve_interface
        result = _resolve_interface("Ethernet")
        assert result == "\\Device\\NPF_AABBCCDD-1111-2222-3333-AABBCCDDEEFF"

    def test_description_resolved_to_guid(self, monkeypatch):
        fake_ifaces = [
            {"name": "eth0", "description": "Intel(R) Ethernet Connection", "guid": "AABBCCDD-0000-0000-0000-AABBCCDDEEFF"},
        ]
        _inject_scapy_mock(monkeypatch, if_list=fake_ifaces)
        from app.capture.adapters.windows.npcap_adapter import _resolve_interface
        result = _resolve_interface("intel(r) ethernet connection")
        assert "NPF_AABBCCDD" in result

    def test_unknown_name_returned_unchanged(self, monkeypatch):
        _inject_scapy_mock(monkeypatch, if_list=[])
        from app.capture.adapters.windows.npcap_adapter import _resolve_interface
        result = _resolve_interface("UnknownAdapter")
        assert result == "UnknownAdapter"

    def test_scapy_import_error_returns_name(self, monkeypatch):
        _inject_scapy_mock(monkeypatch, raise_import=True)
        from app.capture.adapters.windows.npcap_adapter import _resolve_interface
        result = _resolve_interface("Ethernet")
        assert result == "Ethernet"


# ---------------------------------------------------------------------------
# _check_npcap_available
# ---------------------------------------------------------------------------

class TestCheckNpcapAvailable:
    def test_returns_true_when_scapy_lists_interfaces(self, monkeypatch):
        fake_iface = {"name": "Ethernet", "guid": "AABBCCDD-0000-0000-0000-000000000001"}
        _inject_scapy_mock(monkeypatch, if_list=[fake_iface])
        from app.capture.adapters.windows.npcap_adapter import _check_npcap_available
        assert _check_npcap_available() is True

    def test_returns_false_when_list_is_empty(self, monkeypatch):
        _inject_scapy_mock(monkeypatch, if_list=[])
        from app.capture.adapters.windows.npcap_adapter import _check_npcap_available
        assert _check_npcap_available() is False

    def test_returns_false_on_import_error(self, monkeypatch):
        _inject_scapy_mock(monkeypatch, raise_import=True)
        from app.capture.adapters.windows.npcap_adapter import _check_npcap_available
        assert _check_npcap_available() is False


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------

class TestFactoryWindowsLive:
    def test_factory_returns_windows_npcap_capture(self):
        from app.capture.factory import build_capture_adapter
        from app.capture.adapters.windows.npcap_adapter import WindowsNpcapCapture
        adapter = build_capture_adapter("windows_live")
        assert isinstance(adapter, WindowsNpcapCapture)

    def test_factory_respects_interface_name_from_settings(self):
        from app.capture.factory import build_capture_adapter
        from app.contracts.schemas import AppSettings
        settings = AppSettings(run_mode="windows_live", interface_name="Wi-Fi")
        adapter = build_capture_adapter("windows_live", settings=settings)
        assert adapter._interfaces == ["Wi-Fi"]

    def test_factory_respects_interface_names_list(self):
        from app.capture.factory import build_capture_adapter
        from app.contracts.schemas import AppSettings
        settings = AppSettings(run_mode="windows_live", interface_names=["Ethernet", "Wi-Fi"])
        adapter = build_capture_adapter("windows_live", settings=settings)
        assert "Ethernet" in adapter._interfaces
        assert "Wi-Fi" in adapter._interfaces
