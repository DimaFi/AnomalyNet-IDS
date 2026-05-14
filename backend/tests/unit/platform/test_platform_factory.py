"""
Unit tests for platform/__init__.py factory functions.

Tests that:
  - get_capabilities() returns PlatformCapabilities without crashing
  - get_service_manager() returns a valid AbstractServiceManager
  - get_firewall() returns a valid BaseFirewall
  - on non-Linux platform (simulated): MockFirewall returned
  - capabilities are JSON-serializable
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from app.platform.base.capabilities import PlatformCapabilities
from app.platform.base.service_mgr import AbstractServiceManager, NullServiceManager
from app.security.blocker import BaseFirewall, MockFirewall


class TestGetCapabilities:
    def test_returns_platform_capabilities(self):
        from app.platform import get_capabilities
        caps = get_capabilities()
        assert isinstance(caps, PlatformCapabilities)

    def test_platform_field_is_set(self):
        from app.platform import get_capabilities
        caps = get_capabilities()
        assert caps.platform in ("linux", "windows", "darwin", "unknown")

    def test_unknown_platform_returns_mock_mode(self):
        from app.platform import get_capabilities
        with patch("app.platform._platform.system", return_value="FreeBSD"):
            caps = get_capabilities()
        assert caps.capture_backend == "mock"
        assert caps.firewall_backend == "mock"
        assert len(caps.warnings) > 0

    def test_to_dict_is_json_serializable(self):
        import json
        from app.platform import get_capabilities
        caps = get_capabilities()
        serialized = json.dumps(caps.to_dict())
        assert len(serialized) > 10


class TestGetServiceManager:
    def test_returns_abstract_service_manager(self):
        from app.platform import get_service_manager
        mgr = get_service_manager()
        assert isinstance(mgr, AbstractServiceManager)

    def test_null_manager_on_unknown_platform(self):
        from app.platform import get_service_manager
        with patch("app.platform._platform.system", return_value="FreeBSD"):
            mgr = get_service_manager()
        assert isinstance(mgr, NullServiceManager)
        available, enabled = mgr.get_autostart_status()
        assert available is False
        assert enabled is False

    def test_null_manager_set_autostart_returns_false(self):
        mgr = NullServiceManager()
        ok, msg = mgr.set_autostart(True)
        assert ok is False
        assert isinstance(msg, str)

    def test_null_manager_restart_returns_false(self):
        mgr = NullServiceManager()
        assert mgr.restart_service() is False


class TestGetFirewall:
    def test_returns_base_firewall(self):
        from app.platform import get_firewall
        fw = get_firewall()
        assert isinstance(fw, BaseFirewall)

    def test_mock_firewall_on_unknown_platform(self):
        from app.platform import get_firewall
        with patch("app.platform._platform.system", return_value="FreeBSD"):
            fw = get_firewall()
        assert isinstance(fw, MockFirewall)

    def test_mock_firewall_block_unblock(self):
        fw = MockFirewall()
        assert fw.block_ip("10.0.0.1") is True
        assert "10.0.0.1" in fw.list_rules()
        assert fw.unblock_ip("10.0.0.1") is True
        assert "10.0.0.1" not in fw.list_rules()

    def test_windows_platform_returns_mock_in_phase1(self):
        """Phase 2.0.0: Windows returns MockFirewall (netsh not yet implemented)."""
        from app.platform import get_firewall
        with patch("app.platform._platform.system", return_value="Windows"):
            fw = get_firewall()
        assert isinstance(fw, MockFirewall)
