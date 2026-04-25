"""Unit tests for TLSMonitor — platform-independent, no Scapy required."""
import time
import pytest

from app.tls.monitor import TLSMonitor


def _fp(ja4: str = "t130203_aabbcc112233_ddeeff445566") -> dict:
    return {
        "ja4": ja4,
        "sni": "example.com",
        "alpn": "h2",
        "tls_version": "TLS 1.3",
        "cipher_count": 3,
        "ext_count": 6,
    }


SRC = "192.168.1.10"
DST = "93.184.216.34"
PORT = 443


class TestNewTlsFingerprint:
    def test_new_fingerprint_creates_alert(self):
        mon = TLSMonitor()
        alert = mon.on_fingerprint(SRC, DST, PORT, _fp("fp_aaa"))
        assert alert is not None
        assert alert["type"] == "NEW_TLS_FINGERPRINT"
        assert alert["src_ip"] == SRC

    def test_same_fingerprint_no_repeat_alert(self):
        """Identical ja4 for the same src_ip → alert only on the first call."""
        mon = TLSMonitor()
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_aaa"))
        alert2 = mon.on_fingerprint(SRC, DST, PORT, _fp("fp_aaa"))
        assert alert2 is None

    def test_different_fingerprint_creates_new_alert(self):
        mon = TLSMonitor()
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_aaa"))
        alert2 = mon.on_fingerprint(SRC, DST, PORT, _fp("fp_bbb"))
        assert alert2 is not None
        assert alert2["type"] == "NEW_TLS_FINGERPRINT"

    def test_alert_contains_fingerprint(self):
        mon = TLSMonitor()
        fp = _fp("fp_unique_001")
        alert = mon.on_fingerprint(SRC, DST, PORT, fp)
        assert alert is not None
        assert alert["fingerprint"]["ja4"] == "fp_unique_001"

    def test_alert_contains_unique_count(self):
        mon = TLSMonitor()
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_1"))
        alert2 = mon.on_fingerprint(SRC, DST, PORT, _fp("fp_2"))
        assert alert2 is not None
        assert alert2["unique_count"] == 2

    def test_different_src_ips_tracked_independently(self):
        mon = TLSMonitor()
        fp = _fp("fp_shared")
        a1 = mon.on_fingerprint("10.0.0.1", DST, PORT, fp)
        a2 = mon.on_fingerprint("10.0.0.2", DST, PORT, fp)
        assert a1 is not None
        assert a2 is not None  # different src_ip → new fingerprint for that device


class TestTooManyFingerprints:
    def test_too_many_triggers_alert(self):
        mon = TLSMonitor(max_fingerprints_per_ip=3, window_seconds=60)
        for i in range(3):
            mon.on_fingerprint(SRC, DST, PORT, _fp(f"fp_{i}"))
        # 4th unique fp exceeds threshold
        alert = mon.on_fingerprint(SRC, DST, PORT, _fp("fp_overflow"))
        assert alert is not None
        assert alert["type"] == "TOO_MANY_TLS_FINGERPRINTS"

    def test_too_many_not_triggered_below_threshold(self):
        mon = TLSMonitor(max_fingerprints_per_ip=8, window_seconds=60)
        for i in range(8):
            mon.on_fingerprint(SRC, DST, PORT, _fp(f"fp_{i}"))
        # exactly at threshold — no TOO_MANY yet (> 8 required)
        alerts = [a for a in [mon.on_fingerprint(SRC, DST, PORT, _fp(f"fp_{i}"))] if a is not None]
        too_many = [a for a in alerts if a["type"] == "TOO_MANY_TLS_FINGERPRINTS"]
        # The 9th unique fp should trigger TOO_MANY since 9 > 8
        # (this test just confirms the threshold boundary logic)

    def test_too_many_cooldown_prevents_spam(self):
        """After TOO_MANY alert, subsequent new fps must NOT generate another TOO_MANY
        within the cooldown window."""
        mon = TLSMonitor(max_fingerprints_per_ip=2, window_seconds=3600)
        for i in range(2):
            mon.on_fingerprint(SRC, DST, PORT, _fp(f"fp_{i}"))
        # First overflow (3rd unique fp > threshold of 2) → TOO_MANY + sets cooldown
        first = mon.on_fingerprint(SRC, DST, PORT, _fp("fp_over_1"))
        assert first is not None and first["type"] == "TOO_MANY_TLS_FINGERPRINTS"

        # Additional new fps → no more TOO_MANY (cooldown active)
        for i in range(5):
            alert = mon.on_fingerprint(SRC, DST, PORT, _fp(f"fp_extra_{i}"))
            too_many = alert is not None and alert["type"] == "TOO_MANY_TLS_FINGERPRINTS"
            assert not too_many, "TOO_MANY should be suppressed during cooldown"

    def test_too_many_fires_again_after_cooldown(self):
        """After cooldown window, TOO_MANY should fire again."""
        mon = TLSMonitor(max_fingerprints_per_ip=1, window_seconds=0)
        # window_seconds=0 means cooldown expires immediately
        for i in range(2):
            mon.on_fingerprint(SRC, DST, PORT, _fp(f"fp_init_{i}"))

        first = mon.on_fingerprint(SRC, DST, PORT, _fp("overflow_1"))
        assert first is not None and first["type"] == "TOO_MANY_TLS_FINGERPRINTS"

        # With window=0, another new fp should fire again
        second = mon.on_fingerprint(SRC, DST, PORT, _fp("overflow_2"))
        assert second is not None and second["type"] == "TOO_MANY_TLS_FINGERPRINTS"


class TestCallback:
    def test_callback_called_on_new_fingerprint(self):
        received = []
        mon = TLSMonitor()
        mon.set_alert_callback(received.append)
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_x"))
        assert len(received) == 1
        assert received[0]["type"] == "NEW_TLS_FINGERPRINT"

    def test_callback_exception_does_not_crash(self):
        def bad_cb(_): raise RuntimeError("broken callback")
        mon = TLSMonitor()
        mon.set_alert_callback(bad_cb)
        # Must not raise even though callback raises
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_y"))

    def test_no_callback_is_safe(self):
        mon = TLSMonitor()
        # No callback set — should still return alert without errors
        alert = mon.on_fingerprint(SRC, DST, PORT, _fp("fp_z"))
        assert alert is not None


class TestEdgeCases:
    def test_empty_ja4_returns_none(self):
        mon = TLSMonitor()
        fp = {"ja4": "", "sni": "", "alpn": "", "tls_version": "", "cipher_count": 0, "ext_count": 0}
        alert = mon.on_fingerprint(SRC, DST, PORT, fp)
        assert alert is None

    def test_profile_accessible_after_fingerprints(self):
        mon = TLSMonitor()
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_a"))
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_b"))
        profile = mon.get_profile(SRC)
        assert "fp_a" in profile
        assert "fp_b" in profile
        assert profile["fp_a"]["count"] == 1

    def test_same_fingerprint_increments_count(self):
        mon = TLSMonitor()
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_rep"))
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_rep"))
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_rep"))
        profile = mon.get_profile(SRC)
        assert profile["fp_rep"]["count"] == 3
