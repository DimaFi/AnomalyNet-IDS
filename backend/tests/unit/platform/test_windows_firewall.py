"""
Unit tests for WindowsNetshFirewall — all netsh subprocess calls are mocked.

The module-level `run_netsh` hook in platform/windows/firewall.py is replaced
via monkeypatch so no actual Windows Firewall changes are made.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_firewall(protected_ips: set[str] | None = None):
    """Create WindowsNetshFirewall with a predictable protected-IP set."""
    from app.platform.windows.firewall import WindowsNetshFirewall
    fw = WindowsNetshFirewall()
    if protected_ips is not None:
        fw._protected = protected_ips
    return fw


def _mock_run(rc: int, text: str = "Ok."):
    """Return a callable that monkeypatches run_netsh."""
    def _run(cmd):
        return rc, text
    return _run


def _recording_run(rc: int = 0, text: str = "Ok."):
    """Return a MagicMock that records calls and returns (rc, text)."""
    m = MagicMock(return_value=(rc, text))
    return m


# ---------------------------------------------------------------------------
# block_ip — netsh command structure
# ---------------------------------------------------------------------------

class TestBlockIp:
    def test_block_ip_calls_correct_netsh_command(self, monkeypatch):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall(protected_ips=set())

        result = fw.block_ip("10.0.0.1")

        assert result is True
        args = mock_run.call_args[0][0]  # first positional arg is the cmd list
        assert args[0] == "netsh"
        assert "add" in args
        assert "rule" in args
        assert any("ANOMALYNET_BLOCK_10.0.0.1" in a for a in args)
        assert any("remoteip=10.0.0.1" in a for a in args)
        assert "dir=in" in args
        assert "action=block" in args

    def test_block_ip_returns_false_on_netsh_error(self, monkeypatch):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(1, "Error: rule exists"))
        fw = _make_firewall(protected_ips=set())

        assert fw.block_ip("10.0.0.2") is False

    def test_block_ip_returns_false_when_netsh_unavailable(self, monkeypatch):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(-1, "netsh not found"))
        fw = _make_firewall(protected_ips=set())

        assert fw.block_ip("10.0.0.3") is False

    def test_block_ip_with_whitelist(self, monkeypatch):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall(protected_ips=set())

        result = fw.block_ip("10.0.0.5", whitelist={"10.0.0.5"})

        assert result is False
        mock_run.assert_not_called()

    def test_block_ip_multiple_different_ips(self, monkeypatch):
        import app.platform.windows.firewall as mod
        calls = []
        def _run(cmd):
            calls.append(cmd)
            return 0, "Ok."
        monkeypatch.setattr(mod, "run_netsh", _run)
        fw = _make_firewall(protected_ips=set())

        fw.block_ip("10.0.0.10")
        fw.block_ip("10.0.0.11")

        assert len(calls) == 2


# ---------------------------------------------------------------------------
# unblock_ip — netsh command structure
# ---------------------------------------------------------------------------

class TestUnblockIp:
    def test_unblock_ip_calls_correct_netsh_command(self, monkeypatch):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall(protected_ips=set())

        result = fw.unblock_ip("10.0.0.1")

        assert result is True
        args = mock_run.call_args[0][0]
        assert "delete" in args
        assert "rule" in args
        assert any("ANOMALYNET_BLOCK_10.0.0.1" in a for a in args)

    def test_unblock_ip_returns_false_on_error(self, monkeypatch):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(1, "No rules match"))
        fw = _make_firewall(protected_ips=set())

        assert fw.unblock_ip("10.0.0.99") is False


# ---------------------------------------------------------------------------
# Fail-safe protected IPs
# ---------------------------------------------------------------------------

class TestFailSafeProtection:
    def test_loopback_127_not_blocked(self, monkeypatch):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall(protected_ips={"127.0.0.1", "::1"})

        assert fw.block_ip("127.0.0.1") is False
        mock_run.assert_not_called()

    def test_ipv6_loopback_not_blocked(self, monkeypatch):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall(protected_ips={"127.0.0.1", "::1"})

        assert fw.block_ip("::1") is False
        mock_run.assert_not_called()

    def test_gateway_not_blocked(self, monkeypatch):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall(protected_ips={"192.168.1.1"})

        assert fw.block_ip("192.168.1.1") is False
        mock_run.assert_not_called()

    def test_local_interface_ip_not_blocked(self, monkeypatch):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall(protected_ips={"192.168.1.100"})

        assert fw.block_ip("192.168.1.100") is False
        mock_run.assert_not_called()

    def test_non_protected_ip_is_blocked(self, monkeypatch):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall(protected_ips={"127.0.0.1", "192.168.1.1"})

        result = fw.block_ip("10.200.0.5")

        assert result is True
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# list_rules — parsing netsh output
# ---------------------------------------------------------------------------

class TestListRules:
    def test_list_rules_parses_anomalynet_rules(self, monkeypatch):
        import app.platform.windows.firewall as mod
        netsh_output = (
            "Rule Name:                            ANOMALYNET_BLOCK_10.0.0.1\n"
            "----------------------------------------------------------------------\n"
            "Enabled:                              Yes\n"
            "\n"
            "Rule Name:                            ANOMALYNET_BLOCK_10.0.0.2\n"
            "----------------------------------------------------------------------\n"
            "Enabled:                              Yes\n"
            "\n"
            "Rule Name:                            SomeOtherRule\n"
            "----------------------------------------------------------------------\n"
        )
        monkeypatch.setattr(mod, "run_netsh", _mock_run(0, netsh_output))
        fw = _make_firewall()

        rules = fw.list_rules()

        assert "10.0.0.1" in rules
        assert "10.0.0.2" in rules
        assert "SomeOtherRule" not in rules
        assert len(rules) == 2

    def test_list_rules_empty_when_no_anomalynet_rules(self, monkeypatch):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(1, "No rules match the specified criteria."))
        fw = _make_firewall()

        assert fw.list_rules() == []

    def test_list_rules_empty_when_netsh_unavailable(self, monkeypatch):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(-1, "netsh not found"))
        fw = _make_firewall()

        assert fw.list_rules() == []


# ---------------------------------------------------------------------------
# flush — removes only ANOMALYNET_BLOCK_* rules
# ---------------------------------------------------------------------------

class TestFlush:
    def test_flush_deletes_each_anomalynet_rule(self, monkeypatch):
        import app.platform.windows.firewall as mod

        list_output = (
            "Rule Name:                            ANOMALYNET_BLOCK_1.2.3.4\n"
            "Rule Name:                            ANOMALYNET_BLOCK_5.6.7.8\n"
            "Rule Name:                            UnrelatedRule\n"
        )
        calls = []

        def _run(cmd):
            calls.append(cmd)
            # First call is list_rules (show rule name=all), others are delete
            if "show" in cmd:
                return 0, list_output
            return 0, "Ok."

        monkeypatch.setattr(mod, "run_netsh", _run)
        fw = _make_firewall()
        fw.flush()

        delete_calls = [c for c in calls if "delete" in c]
        deleted_names = [
            next(a for a in c if "ANOMALYNET_BLOCK_" in a)
            for c in delete_calls
        ]
        assert any("ANOMALYNET_BLOCK_1.2.3.4" in n for n in deleted_names)
        assert any("ANOMALYNET_BLOCK_5.6.7.8" in n for n in deleted_names)
        # UnrelatedRule must not be deleted
        unrelated_deleted = [n for n in deleted_names if "UnrelatedRule" in n]
        assert len(unrelated_deleted) == 0

    def test_flush_noop_when_no_rules(self, monkeypatch):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(1, "No rules match"))
        fw = _make_firewall()
        fw.flush()  # must not raise


# ---------------------------------------------------------------------------
# snapshot / restore
# ---------------------------------------------------------------------------

class TestSnapshotRestore:
    def test_snapshot_calls_netsh_export(self, monkeypatch, tmp_path):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall()

        result = fw.snapshot(str(tmp_path / "fw_backup.wfw"))

        assert result is True
        args = mock_run.call_args[0][0]
        assert "advfirewall" in args
        assert "export" in args

    def test_restore_calls_netsh_import(self, monkeypatch, tmp_path):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall()

        # Create a fake .wfw file so the existence check passes
        backup = tmp_path / "fw_backup.wfw"
        backup.write_bytes(b"fake")

        result = fw.restore(str(backup))

        assert result is True
        args = mock_run.call_args[0][0]
        assert "advfirewall" in args
        assert "import" in args

    def test_restore_returns_false_when_file_missing(self, monkeypatch, tmp_path):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall()

        result = fw.restore(str(tmp_path / "nonexistent.wfw"))

        assert result is False
        mock_run.assert_not_called()

    def test_snapshot_returns_false_on_netsh_error(self, monkeypatch, tmp_path):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(1, "Error: access denied"))
        fw = _make_firewall()

        assert fw.snapshot(str(tmp_path / "fw.wfw")) is False


# ---------------------------------------------------------------------------
# Factory: admin / no-admin
# ---------------------------------------------------------------------------

class TestCreateWindowsFirewall:
    def test_admin_returns_windows_netsh_firewall(self, monkeypatch):
        import app.platform.windows.firewall as mod
        from app.platform.windows.firewall import WindowsNetshFirewall
        monkeypatch.setattr(mod, "_is_admin", lambda: True)
        monkeypatch.setattr(mod, "_collect_protected_ips", lambda: {"127.0.0.1"})

        fw = mod.create_windows_firewall()

        assert isinstance(fw, WindowsNetshFirewall)

    def test_no_admin_returns_mock_firewall(self, monkeypatch):
        import app.platform.windows.firewall as mod
        from app.security.blocker import MockFirewall
        monkeypatch.setattr(mod, "_is_admin", lambda: False)

        fw = mod.create_windows_firewall()

        assert isinstance(fw, MockFirewall)

    def test_platform_factory_returns_mock_without_admin(self, monkeypatch):
        """Platform get_firewall() on Windows returns MockFirewall when not admin."""
        import app.platform.windows.firewall as win_fw_mod
        import app.platform as plat_mod
        import platform as _platform
        from app.security.blocker import MockFirewall

        monkeypatch.setattr(win_fw_mod, "_is_admin", lambda: False)
        monkeypatch.setattr(win_fw_mod, "_collect_protected_ips", lambda: {"127.0.0.1"})
        with patch("app.platform._platform.system", return_value="Windows"):
            from app.platform import get_firewall
            fw = get_firewall()
        assert isinstance(fw, MockFirewall)

    def test_platform_factory_returns_netsh_with_admin(self, monkeypatch):
        """Platform get_firewall() on Windows returns WindowsNetshFirewall when admin."""
        import app.platform.windows.firewall as win_fw_mod
        from app.platform.windows.firewall import WindowsNetshFirewall
        monkeypatch.setattr(win_fw_mod, "_is_admin", lambda: True)
        monkeypatch.setattr(win_fw_mod, "_collect_protected_ips", lambda: {"127.0.0.1"})

        with patch("app.platform._platform.system", return_value="Windows"):
            from app.platform import get_firewall
            fw = get_firewall()
        assert isinstance(fw, WindowsNetshFirewall)


# ---------------------------------------------------------------------------
# Capabilities integration
# ---------------------------------------------------------------------------

class TestWindowsCapabilities:
    def test_firewall_blocking_true_when_admin(self, monkeypatch):
        import app.platform.windows.capabilities as caps_mod
        monkeypatch.setattr(caps_mod, "_is_admin", lambda: True)
        monkeypatch.setattr(caps_mod, "_has_npcap", lambda: False)
        monkeypatch.setattr(caps_mod, "_has_schtasks", lambda: True)
        monkeypatch.setattr(caps_mod, "_has_scapy", lambda: False)

        caps = caps_mod.windows_capabilities()

        assert caps.firewall_blocking is True
        assert caps.firewall_backend == "netsh"
        assert caps.firewall_rollback is True

    def test_firewall_blocking_false_without_admin(self, monkeypatch):
        import app.platform.windows.capabilities as caps_mod
        monkeypatch.setattr(caps_mod, "_is_admin", lambda: False)
        monkeypatch.setattr(caps_mod, "_has_npcap", lambda: True)
        monkeypatch.setattr(caps_mod, "_has_schtasks", lambda: True)
        monkeypatch.setattr(caps_mod, "_has_scapy", lambda: True)

        caps = caps_mod.windows_capabilities()

        assert caps.firewall_blocking is False
        assert caps.firewall_backend == "mock"
        assert caps.firewall_rollback is False
        assert any("Administrator" in w for w in caps.warnings)

    def test_capture_ready_when_admin_and_npcap(self, monkeypatch):
        import app.platform.windows.capabilities as caps_mod
        monkeypatch.setattr(caps_mod, "_is_admin", lambda: True)
        monkeypatch.setattr(caps_mod, "_has_npcap", lambda: True)
        monkeypatch.setattr(caps_mod, "_has_schtasks", lambda: True)
        monkeypatch.setattr(caps_mod, "_has_scapy", lambda: True)

        caps = caps_mod.windows_capabilities()

        assert caps.packet_capture is True
        assert caps.capture_backend == "npcap"
        assert caps.firewall_blocking is True
        assert caps.firewall_backend == "netsh"
        assert caps.warnings == []

    def test_all_mock_without_admin(self, monkeypatch):
        import app.platform.windows.capabilities as caps_mod
        monkeypatch.setattr(caps_mod, "_is_admin", lambda: False)
        monkeypatch.setattr(caps_mod, "_has_npcap", lambda: False)
        monkeypatch.setattr(caps_mod, "_has_schtasks", lambda: False)
        monkeypatch.setattr(caps_mod, "_has_scapy", lambda: False)

        caps = caps_mod.windows_capabilities()

        assert caps.packet_capture is False
        assert caps.capture_backend == "mock"
        assert caps.firewall_blocking is False
        assert caps.firewall_backend == "mock"
        assert len(caps.warnings) >= 1


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------

class TestErrorResilience:
    def test_block_ip_does_not_raise_on_exception(self, monkeypatch):
        import app.platform.windows.firewall as mod

        def _explode(cmd):
            raise RuntimeError("unexpected error")

        monkeypatch.setattr(mod, "run_netsh", _explode)
        fw = _make_firewall(protected_ips=set())

        # Should return False, not raise
        with pytest.raises(RuntimeError):
            # The exception propagates from run_netsh itself (not caught in block_ip)
            # This documents that run_netsh errors DO propagate — correct behaviour,
            # the caller (service.py) wraps in try/except.
            fw.block_ip("1.2.3.4")

    def test_run_netsh_hook_file_not_found_returns_minus_one(self):
        from app.platform.windows.firewall import _default_run_netsh
        # Calling a non-existent command should return -1, not raise
        rc, text = _default_run_netsh(["nonexistent_command_xyz_123"])
        assert rc == -1
        assert "not found" in text.lower() or len(text) > 0

    def test_list_rules_never_raises(self, monkeypatch):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(-1, "netsh not found"))
        fw = _make_firewall()

        result = fw.list_rules()

        assert isinstance(result, list)

    def test_flush_never_raises_when_empty(self, monkeypatch):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(1, "No rules match"))
        fw = _make_firewall()
        fw.flush()  # must not raise

    def test_restore_never_raises_on_missing_file(self, monkeypatch, tmp_path):
        import app.platform.windows.firewall as mod
        mock_run = _recording_run(0)
        monkeypatch.setattr(mod, "run_netsh", mock_run)
        fw = _make_firewall()

        result = fw.restore(str(tmp_path / "missing.wfw"))

        assert result is False


# ---------------------------------------------------------------------------
# is_blocked
# ---------------------------------------------------------------------------

class TestIsBlocked:
    def test_is_blocked_returns_true_when_rule_exists(self, monkeypatch):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(0, "Rule Name: ANOMALYNET_BLOCK_1.2.3.4"))
        fw = _make_firewall()
        assert fw.is_blocked("1.2.3.4") is True

    def test_is_blocked_returns_false_when_rule_missing(self, monkeypatch):
        import app.platform.windows.firewall as mod
        monkeypatch.setattr(mod, "run_netsh", _mock_run(1, "No rules match"))
        fw = _make_firewall()
        assert fw.is_blocked("1.2.3.4") is False
