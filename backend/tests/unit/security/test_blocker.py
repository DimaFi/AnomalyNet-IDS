"""Unit tests for app.security.blocker — mocks run_command, no real iptables."""
import pytest
from unittest.mock import patch, call

import app.security.blocker as blocker_module
from app.security.blocker import LinuxFirewall, MockFirewall, create_firewall


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(_cmd):
    return (0, "")


def _fail(_cmd):
    return (1, "error")


# ── MockFirewall tests ────────────────────────────────────────────────────────

class TestMockFirewall:
    def test_block_returns_true(self):
        fw = MockFirewall()
        assert fw.block_ip("1.2.3.4") is True

    def test_block_whitelist_rejected(self):
        fw = MockFirewall()
        assert fw.block_ip("1.2.3.4", whitelist={"1.2.3.4"}) is False

    def test_unblock_returns_true(self):
        fw = MockFirewall()
        fw.block_ip("1.2.3.4")
        assert fw.unblock_ip("1.2.3.4") is True

    def test_list_rules(self):
        fw = MockFirewall()
        fw.block_ip("1.2.3.4")
        fw.block_ip("5.6.7.8")
        assert set(fw.list_rules()) == {"1.2.3.4", "5.6.7.8"}

    def test_flush_clears(self):
        fw = MockFirewall()
        fw.block_ip("1.2.3.4")
        fw.flush()
        assert fw.list_rules() == []

    def test_snapshot_noop(self, tmp_path):
        fw = MockFirewall()
        assert fw.snapshot(str(tmp_path / "backup")) is True

    def test_restore_noop(self, tmp_path):
        fw = MockFirewall()
        assert fw.restore(str(tmp_path / "backup")) is True

    def test_warnings_present(self):
        fw = MockFirewall()
        assert len(fw.get_warnings()) > 0


# ── LinuxFirewall tests ───────────────────────────────────────────────────────

class TestLinuxFirewallPcMode:
    """PC mode — uses ANOMALYNET_INPUT chain + INPUT jump."""

    def _make_fw(self, run_fn=None):
        fw = LinuxFirewall(blocking_mode="pc")
        # Mark chain as ready to skip chain creation in most tests
        fw._chain_ready = True
        fw._protected = set()  # clear local-IP protection for predictable tests
        if run_fn is not None:
            blocker_module.run_command = run_fn
        return fw

    def teardown_method(self, _):
        # Restore default
        blocker_module.run_command = blocker_module._default_run

    def test_block_calls_input_chain(self):
        calls = []
        def record(cmd):
            calls.append(cmd)
            return (0, "")
        blocker_module.run_command = record
        fw = self._make_fw()
        fw.block_ip("10.0.0.1")
        assert ["iptables", "-A", "ANOMALYNET_INPUT", "-s", "10.0.0.1", "-j", "DROP"] in calls

    def test_block_whitelist_rejected(self):
        called = []
        blocker_module.run_command = lambda cmd: (called.append(cmd), (0, ""))[1]
        fw = self._make_fw()
        result = fw.block_ip("10.0.0.1", whitelist={"10.0.0.1"})
        assert result is False
        assert not any("10.0.0.1" in str(c) for c in called)

    def test_block_fail_returns_false(self):
        blocker_module.run_command = lambda _: (1, "permission denied")
        fw = self._make_fw()
        assert fw.block_ip("10.0.0.1") is False

    def test_unblock_calls_input_chain(self):
        calls = []
        def record(cmd):
            calls.append(cmd)
            return (0, "")
        blocker_module.run_command = record
        fw = self._make_fw()
        fw.unblock_ip("10.0.0.1")
        assert ["iptables", "-D", "ANOMALYNET_INPUT", "-s", "10.0.0.1", "-j", "DROP"] in calls

    def test_flush_calls_anomalynet_input(self):
        calls = []
        def record(cmd):
            calls.append(cmd)
            return (0, "")
        blocker_module.run_command = record
        fw = self._make_fw()
        fw.flush()
        assert ["iptables", "-F", "ANOMALYNET_INPUT"] in calls


class TestLinuxFirewallGatewayMode:
    """Gateway mode — uses ANOMALYNET_FORWARD chain + FORWARD jump."""

    def _make_fw(self, run_fn=None):
        fw = LinuxFirewall(blocking_mode="gateway")
        fw._chain_ready = True
        fw._protected = set()
        if run_fn is not None:
            blocker_module.run_command = run_fn
        return fw

    def teardown_method(self, _):
        blocker_module.run_command = blocker_module._default_run

    def test_block_calls_forward_chain(self):
        calls = []
        def record(cmd):
            calls.append(cmd)
            return (0, "")
        blocker_module.run_command = record
        fw = self._make_fw()
        fw.block_ip("10.0.0.2")
        assert ["iptables", "-A", "ANOMALYNET_FORWARD", "-s", "10.0.0.2", "-j", "DROP"] in calls

    def test_flush_calls_forward_chain(self):
        calls = []
        blocker_module.run_command = lambda cmd: (calls.append(cmd), (0, ""))[1]
        fw = self._make_fw()
        fw.flush()
        assert ["iptables", "-F", "ANOMALYNET_FORWARD"] in calls


class TestLinuxFirewallChainSetup:
    """Chain creation and jump insertion."""

    def teardown_method(self, _):
        blocker_module.run_command = blocker_module._default_run

    def test_chain_created_if_not_exists(self):
        calls = []
        def record(cmd):
            calls.append(cmd)
            # First call is -L check — return 1 (chain absent)
            if cmd == ["iptables", "-L", "ANOMALYNET_INPUT", "-n"]:
                return (1, "no such chain")
            return (0, "")
        blocker_module.run_command = record

        fw = LinuxFirewall(blocking_mode="pc")
        fw._protected = set()
        fw._ensure_chain()

        assert ["iptables", "-N", "ANOMALYNET_INPUT"] in calls
        assert ["iptables", "-I", "INPUT", "-j", "ANOMALYNET_INPUT"] in calls

    def test_chain_skipped_if_exists(self):
        calls = []
        def record(cmd):
            calls.append(cmd)
            return (0, "")
        blocker_module.run_command = record

        fw = LinuxFirewall(blocking_mode="pc")
        fw._protected = set()
        fw._ensure_chain()

        assert ["iptables", "-N", "ANOMALYNET_INPUT"] not in calls
        assert ["iptables", "-I", "INPUT", "-j", "ANOMALYNET_INPUT"] in calls


class TestLinuxFirewallSnapshot:
    """Snapshot and restore."""

    def teardown_method(self, _):
        blocker_module.run_command = blocker_module._default_run

    def test_restore_returns_false_if_no_file(self, tmp_path):
        fw = LinuxFirewall()
        assert fw.restore(str(tmp_path / "nonexistent.bak")) is False

    def test_restore_returns_false_on_failure(self, tmp_path):
        backup = tmp_path / "backup.bak"
        backup.write_bytes(b"fake data")

        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 1, "stderr": b"error"})()
            fw = LinuxFirewall()
            result = fw.restore(str(backup))
        assert result is False


# ── create_firewall factory ───────────────────────────────────────────────────

def test_create_firewall_returns_mock_on_non_linux():
    with patch("platform.system", return_value="Windows"):
        fw = create_firewall("pc")
    assert isinstance(fw, MockFirewall)


def test_create_firewall_returns_linux_on_linux():
    with patch("platform.system", return_value="Linux"):
        fw = create_firewall("gateway")
    assert isinstance(fw, LinuxFirewall)
    assert fw.blocking_mode == "gateway"
    assert fw._chain == "ANOMALYNET_FORWARD"


# ── sync_rules tests ──────────────────────────────────────────────────────────

class TestSyncRulesMock:
    """sync_rules on MockFirewall — no iptables, pure in-memory."""

    def test_sync_adds_missing_ips(self):
        fw = MockFirewall()
        added = fw.sync_rules(["1.2.3.4", "5.6.7.8"])
        assert added == 2
        assert set(fw.list_rules()) == {"1.2.3.4", "5.6.7.8"}

    def test_sync_no_duplicates(self):
        fw = MockFirewall()
        fw.block_ip("1.2.3.4")
        added = fw.sync_rules(["1.2.3.4", "9.9.9.9"])
        assert added == 1  # only 9.9.9.9 was missing
        assert "1.2.3.4" in fw.list_rules()
        assert "9.9.9.9" in fw.list_rules()

    def test_sync_respects_whitelist(self):
        fw = MockFirewall()
        added = fw.sync_rules(["1.2.3.4", "5.5.5.5"], whitelist={"5.5.5.5"})
        assert added == 1
        assert "5.5.5.5" not in fw.list_rules()

    def test_sync_empty_list_returns_zero(self):
        fw = MockFirewall()
        assert fw.sync_rules([]) == 0

    def test_sync_all_already_present(self):
        fw = MockFirewall()
        fw.block_ip("1.2.3.4")
        fw.block_ip("5.6.7.8")
        added = fw.sync_rules(["1.2.3.4", "5.6.7.8"])
        assert added == 0


class TestSyncRulesLinux:
    """sync_rules on LinuxFirewall — mocked run_command."""

    def teardown_method(self, _):
        blocker_module.run_command = blocker_module._default_run

    def _make_fw(self, mode: str = "pc", existing_ips: list[str] | None = None) -> LinuxFirewall:
        """Create LinuxFirewall with chain ready and optional pre-existing rules."""
        fw = LinuxFirewall(blocking_mode=mode)
        fw._chain_ready = True
        fw._protected = set()

        # Stub list_rules to return existing_ips
        existing = set(existing_ips or [])
        calls_log: list[list[str]] = []

        def _run(cmd: list[str]) -> tuple[int, str]:
            calls_log.append(cmd)
            return (0, "")

        blocker_module.run_command = _run
        fw._calls = calls_log
        fw._existing_stub = existing

        # Override list_rules to return stubbed existing rules
        fw.list_rules = lambda: list(existing)  # type: ignore[method-assign]
        return fw

    def test_sync_pc_mode_adds_to_input_chain(self):
        fw = self._make_fw(mode="pc")
        fw.sync_rules(["10.0.0.1", "10.0.0.2"])
        block_calls = [c for c in fw._calls if "-A" in c]
        assert ["iptables", "-A", "ANOMALYNET_INPUT", "-s", "10.0.0.1", "-j", "DROP"] in block_calls
        assert ["iptables", "-A", "ANOMALYNET_INPUT", "-s", "10.0.0.2", "-j", "DROP"] in block_calls

    def test_sync_gateway_mode_adds_to_forward_chain(self):
        fw = self._make_fw(mode="gateway")
        fw.sync_rules(["10.0.0.5"])
        block_calls = [c for c in fw._calls if "-A" in c]
        assert ["iptables", "-A", "ANOMALYNET_FORWARD", "-s", "10.0.0.5", "-j", "DROP"] in block_calls

    def test_sync_skips_existing_rules(self):
        fw = self._make_fw(existing_ips=["10.0.0.1"])
        added = fw.sync_rules(["10.0.0.1", "10.0.0.2"])
        assert added == 1
        block_calls = [c for c in fw._calls if "-A" in c]
        # 10.0.0.1 already present — should not appear in block calls
        for c in block_calls:
            assert "10.0.0.1" not in c
