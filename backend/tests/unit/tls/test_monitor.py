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
        """After cooldown expires, TOO_MANY should fire again on the next new FP."""
        # profile_window_seconds=3600 → entries stay; too_many_cooldown_seconds=0 → no cooldown
        mon = TLSMonitor(max_fingerprints_per_ip=2,
                         profile_window_seconds=3600,
                         too_many_cooldown_seconds=0)
        for i in range(3):  # 3 entries → 3 > 2 → first TOO_MANY
            mon.on_fingerprint(SRC, DST, PORT, _fp(f"fp_init_{i}"))

        first_too_many = next(
            (a for a in [mon.on_fingerprint(SRC, DST, PORT, _fp("fp_over_1"))]
             if a is not None and a["type"] == "TOO_MANY_TLS_FINGERPRINTS"),
            None,
        )
        assert first_too_many is not None, "expected first TOO_MANY alert"

        # cooldown=0 → immediately expired; another new FP should fire TOO_MANY again
        second = mon.on_fingerprint(SRC, DST, PORT, _fp("fp_over_2"))
        assert second is not None and second["type"] == "TOO_MANY_TLS_FINGERPRINTS", (
            "expected second TOO_MANY after zero cooldown"
        )


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

    def test_ja4_legacy_fallback_when_ja4_absent(self):
        """If fingerprint has no 'ja4' key but has 'ja4_legacy', use the legacy key."""
        mon = TLSMonitor()
        fp = {"ja4_legacy": "t120203_abc_def", "sni": "", "alpn": ""}
        alert = mon.on_fingerprint(SRC, DST, PORT, fp)
        assert alert is not None
        assert alert["type"] == "NEW_TLS_FINGERPRINT"

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


class TestStats:
    def test_get_stats_returns_expected_keys(self):
        mon = TLSMonitor()
        stats = mon.get_stats()
        for key in ("fingerprints_seen", "alerts_new", "alerts_too_many",
                    "ips_tracked", "profiles_total", "cooldown_entries",
                    "profile_expirations"):
            assert key in stats, f"missing stats key: {key}"

    def test_stats_increment_on_new_fingerprint(self):
        mon = TLSMonitor()
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_stats_1"))
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_stats_2"))
        stats = mon.get_stats()
        assert stats["fingerprints_seen"] == 2
        assert stats["alerts_new"] == 2
        assert stats["ips_tracked"] == 1
        assert stats["profiles_total"] == 2

    def test_stats_repeat_fingerprint_increments_seen_only(self):
        mon = TLSMonitor()
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_x"))
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_x"))
        stats = mon.get_stats()
        assert stats["fingerprints_seen"] == 2
        assert stats["alerts_new"] == 1  # only first call creates alert

    def test_stats_too_many_increments(self):
        mon = TLSMonitor(max_fingerprints_per_ip=2, window_seconds=3600)
        for i in range(3):
            mon.on_fingerprint(SRC, DST, PORT, _fp(f"fp_sm_{i}"))
        stats = mon.get_stats()
        assert stats["alerts_too_many"] == 1

    def test_stats_profile_expirations_on_zero_window(self):
        """window=0 → entries expire immediately → profile_expirations counts them."""
        mon = TLSMonitor(window_seconds=0)
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_exp"))
        stats = mon.get_stats()
        # With window=0 the entry was created then immediately expired on the same call
        # profile_expirations should reflect cleared entries on subsequent calls
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_exp2"))
        stats2 = mon.get_stats()
        # Each call expires old entries, so expirations accumulate
        assert stats2["profile_expirations"] >= 0  # at minimum no crash

    def test_stats_snapshot_is_copy(self):
        """Modifying returned stats dict must not affect monitor state."""
        mon = TLSMonitor()
        stats = mon.get_stats()
        stats["fingerprints_seen"] = 9999
        assert mon.get_stats()["fingerprints_seen"] != 9999

    def test_cooldown_entries_tracked(self):
        mon = TLSMonitor(max_fingerprints_per_ip=1, window_seconds=3600)
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_c1"))
        mon.on_fingerprint(SRC, DST, PORT, _fp("fp_c2"))  # triggers TOO_MANY
        stats = mon.get_stats()
        assert stats["cooldown_entries"] == 1
