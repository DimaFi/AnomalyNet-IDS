"""
Unit tests for PlatformCapabilities dataclass and platform detection.
"""

from __future__ import annotations

import pytest
from app.platform.base.capabilities import PlatformCapabilities


class TestPlatformCapabilities:
    def test_default_values(self):
        caps = PlatformCapabilities()
        assert caps.platform == "unknown"
        assert caps.packet_capture is False
        assert caps.firewall_blocking is False
        assert caps.autostart_available is False
        assert caps.current_elevated is False
        assert caps.capture_backend == "mock"
        assert caps.firewall_backend == "mock"
        assert caps.service_backend == "none"
        assert caps.warnings == []

    def test_to_dict_returns_all_fields(self):
        caps = PlatformCapabilities(platform="linux", packet_capture=True)
        d = caps.to_dict()
        assert isinstance(d, dict)
        assert d["platform"] == "linux"
        assert d["packet_capture"] is True
        assert "firewall_blocking" in d
        assert "warnings" in d
        assert isinstance(d["warnings"], list)

    def test_linux_caps_structure(self):
        """linux_capabilities() returns correct structure without crashing."""
        from app.platform.linux.capabilities import linux_capabilities
        caps = linux_capabilities()
        assert caps.platform == "linux"
        # On test runner (likely non-root) capture should be False or depend on env
        assert isinstance(caps.packet_capture, bool)
        assert isinstance(caps.firewall_blocking, bool)
        assert isinstance(caps.warnings, list)
        assert caps.capture_backend in ("scapy_linux", "mock")
        assert caps.firewall_backend in ("iptables", "mock")
        assert caps.service_backend in ("systemd", "none")

    def test_capabilities_json_serializable(self):
        """to_dict() result can be JSON-serialized (needed for /api/capabilities)."""
        import json
        caps = PlatformCapabilities(
            platform="linux",
            packet_capture=True,
            warnings=["test warning"],
        )
        d = caps.to_dict()
        serialized = json.dumps(d)
        assert "linux" in serialized
        assert "test warning" in serialized
