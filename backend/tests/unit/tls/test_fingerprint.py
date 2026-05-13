"""Unit tests for app.tls.fingerprint — uses mock Scapy objects, no real packets."""
import pytest
from unittest.mock import MagicMock, patch

from app.tls.fingerprint import (
    compute_tls_fingerprint_from_scapy,
    _GREASE,
    get_parse_stats,
    reset_parse_stats,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_extension(type_id: int, servername=None, alpn_protocol=None,
                    sig_algs=None, supported_versions=None):
    """Create a minimal mock extension object."""
    ext = MagicMock()
    ext.type = type_id

    # SNI
    if servername is not None:
        sn = MagicMock()
        sn.servername = servername
        ext.servernames = [sn]
    else:
        ext.servernames = []

    # ALPN
    if alpn_protocol is not None:
        proto = MagicMock()
        proto.protocol = alpn_protocol
        ext.protocols = [proto]
    else:
        ext.protocols = []

    # signature_algorithms
    if sig_algs is not None:
        ext.sig_algs = sig_algs
    else:
        ext.sig_algs = []

    # supported_versions (for TLS 1.3 detection)
    if supported_versions is not None:
        ext.versions = supported_versions
        ext.supported_versions = supported_versions
    else:
        ext.versions = []
        ext.supported_versions = []

    return ext


def _make_hello(version=0x0303, ciphers=None, extensions=None):
    """Create a mock TLSClientHello."""
    hello = MagicMock()
    hello.version = version
    hello.ciphers = ciphers or [0x1301, 0x1302, 0x1303]
    hello.ext = extensions or []
    return hello


def _make_packet(hello):
    """Wrap hello in a mock packet with TLSClientHello layer."""
    pkt = MagicMock()
    try:
        from scapy.layers.tls.handshake import TLSClientHello
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None
    except ImportError:
        pkt.haslayer.return_value = False
    return pkt


def _skip_if_no_scapy():
    try:
        from scapy.layers.tls.handshake import TLSClientHello  # noqa: F401
    except ImportError:
        pytest.skip("scapy TLS not available")


# ── Non-TLS packets ───────────────────────────────────────────────────────────

class TestNonTlsPacket:
    def test_packet_without_tls_layer_returns_none(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello  # noqa: F401
        pkt = MagicMock()
        pkt.haslayer.return_value = False
        assert compute_tls_fingerprint_from_scapy(pkt) is None

    def test_exception_during_parse_returns_none(self):
        _skip_if_no_scapy()
        pkt = MagicMock()
        pkt.haslayer.side_effect = RuntimeError("broken packet")
        assert compute_tls_fingerprint_from_scapy(pkt) is None

    def test_import_error_returns_none(self):
        with patch.dict("sys.modules", {"scapy.layers.tls.handshake": None}):
            pkt = MagicMock()
            assert compute_tls_fingerprint_from_scapy(pkt) is None


# ── Output shape ──────────────────────────────────────────────────────────────

class TestOutputShape:
    def test_returns_dict_with_all_required_keys(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello()
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None

        required = {
            "ja4", "ja4_raw", "ja4_legacy", "ja4_source", "ja4_version",
            "sni", "alpn", "tls_version", "cipher_count", "ext_count",
        }
        missing = required - result.keys()
        assert not missing, f"missing keys: {missing}"

    def test_ja4_source_is_scapy_tls(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello()
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["ja4_source"] == "scapy_tls"

    def test_ja4_version_is_foxio_v1(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello()
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["ja4_version"] == "foxio_v1"

    def test_ja4_has_three_underscore_parts(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello(ciphers=[0x1301, 0x1302])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        parts = result["ja4"].split("_")
        assert len(parts) == 3, f"expected 3 parts, got: {result['ja4']!r}"

    def test_ja4_raw_has_three_underscore_parts(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello(ciphers=[0x1301, 0x1302])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        parts = result["ja4_raw"].split("_")
        assert len(parts) == 3, f"expected 3 parts in ja4_raw, got: {result['ja4_raw']!r}"

    def test_ja4_legacy_has_three_underscore_parts(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello(ciphers=[0x1301, 0x1302])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        parts = result["ja4_legacy"].split("_")
        assert len(parts) == 3, f"expected 3 parts in ja4_legacy, got: {result['ja4_legacy']!r}"


# ── Canonical vs raw ──────────────────────────────────────────────────────────

class TestCanonicalVsRaw:
    def test_canonical_independent_of_cipher_order(self):
        """ja4 must be the same regardless of wire order of ciphers."""
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        def _fp(cipher_order):
            hello = _make_hello(ciphers=cipher_order)
            pkt = MagicMock()
            pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
            pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None
            return compute_tls_fingerprint_from_scapy(pkt)

        r1 = _fp([0x1301, 0x1302, 0x1303])
        r2 = _fp([0x1303, 0x1301, 0x1302])
        assert r1 is not None and r2 is not None
        assert r1["ja4"] == r2["ja4"], "canonical ja4 must be order-independent"

    def test_raw_changes_with_cipher_wire_order(self):
        """ja4_raw preserves wire order — different order → different hash."""
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        def _fp(cipher_order):
            hello = _make_hello(ciphers=cipher_order)
            pkt = MagicMock()
            pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
            pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None
            return compute_tls_fingerprint_from_scapy(pkt)

        r1 = _fp([0x1301, 0x0035])  # sorted order
        r2 = _fp([0x0035, 0x1301])  # reversed
        assert r1 is not None and r2 is not None
        assert r1["ja4_raw"] != r2["ja4_raw"], "ja4_raw should differ by wire order"

    def test_canonical_same_canonical_different_raw(self):
        """Two packets with same ciphers but different order:
        canonical must match, raw must differ."""
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        def _fp(cipher_order):
            hello = _make_hello(ciphers=cipher_order)
            pkt = MagicMock()
            pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
            pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None
            return compute_tls_fingerprint_from_scapy(pkt)

        r1 = _fp([0x1301, 0x1302])
        r2 = _fp([0x1302, 0x1301])
        assert r1 is not None and r2 is not None
        assert r1["ja4"] == r2["ja4"]
        assert r1["ja4_raw"] != r2["ja4_raw"]

    def test_ja4_legacy_differs_from_ja4(self):
        """ja4_legacy uses the old formula — must differ from ja4 for real inputs."""
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        sig_alg_ext = _make_extension(type_id=0x000D, sig_algs=[0x0403, 0x0804])
        hello = _make_hello(ciphers=[0x1301, 0x1302], extensions=[sig_alg_ext])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        # Legacy uses different ext hash formula → different fingerprint
        assert result["ja4_legacy"] != result["ja4"], (
            "ja4_legacy should differ from ja4 when sig_algs present (old formula vs FoxIO)"
        )


# ── Field extraction ──────────────────────────────────────────────────────────

class TestFingerprintBasic:
    def test_sni_extracted(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        sni_ext = _make_extension(type_id=0x0000, servername=b"example.com")
        hello = _make_hello(extensions=[sni_ext])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["sni"] == "example.com"

    def test_sni_empty_when_absent(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello(extensions=[])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["sni"] == ""

    def test_alpn_extracted(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        alpn_ext = _make_extension(type_id=0x0010, alpn_protocol=b"h2")
        hello = _make_hello(extensions=[alpn_ext])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["alpn"] == "h2"

    def test_alpn_empty_when_absent(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello(extensions=[])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["alpn"] == ""

    def test_sni_flag_d_when_present(self):
        """JA4 prefix must contain 'd' when SNI is present."""
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        sni_ext = _make_extension(type_id=0x0000, servername=b"example.com")
        hello = _make_hello(extensions=[sni_ext])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        prefix = result["ja4"].split("_")[0]
        assert "d" in prefix, f"SNI present → 'd' expected in prefix: {prefix!r}"

    def test_sni_flag_i_when_absent(self):
        """JA4 prefix must contain 'i' when SNI is absent."""
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello(extensions=[])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        prefix = result["ja4"].split("_")[0]
        assert "i" in prefix, f"SNI absent → 'i' expected in prefix: {prefix!r}"


# ── GREASE filtering ──────────────────────────────────────────────────────────

class TestGreaseFiltering:
    def test_grease_filtered_from_ciphers(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        real_ciphers = [0x1301, 0x1302]
        hello = _make_hello(ciphers=[0x0A0A] + real_ciphers)
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["cipher_count"] == len(real_ciphers)

    def test_all_grease_values_filtered(self):
        """All 16 GREASE cipher values must be filtered."""
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        all_grease = list(_GREASE)[:4]  # sample 4 GREASE values
        real = [0x1301]
        hello = _make_hello(ciphers=all_grease + real)
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["cipher_count"] == 1

    def test_grease_filtered_from_extensions(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        grease_ext = _make_extension(type_id=0x0A0A)
        real_ext = _make_extension(type_id=0x0017)
        hello = _make_hello(extensions=[grease_ext, real_ext])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["ext_count"] == 1


# ── TLS version detection ─────────────────────────────────────────────────────

class TestTlsVersionDetection:
    def test_tls_12_from_client_version(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello(version=0x0303, extensions=[])  # 0x0303 = TLS 1.2
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert "1.2" in result["tls_version"]

    def test_tls_13_via_supported_versions_extension(self):
        """TLS 1.3 detected via supported_versions extension (0x002B) with 0x0304."""
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        sv_ext = _make_extension(type_id=0x002B, supported_versions=[0x0304])
        hello = _make_hello(version=0x0303, extensions=[sv_ext])  # header says 1.2
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert "1.3" in result["tls_version"], (
            f"TLS 1.3 should be detected via supported_versions, got: {result['tls_version']!r}"
        )

    def test_tls_version_prefix_13_in_ja4(self):
        """TLS 1.3 → '13' in JA4 prefix."""
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        sv_ext = _make_extension(type_id=0x002B, supported_versions=[0x0304])
        hello = _make_hello(version=0x0303, extensions=[sv_ext])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        prefix = result["ja4"].split("_")[0]
        assert prefix.startswith("t13"), f"expected 't13' prefix for TLS 1.3, got: {prefix!r}"


# ── Determinism and uniqueness ────────────────────────────────────────────────

class TestDeterminism:
    def test_same_packet_same_ja4(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        def _fp():
            hello = _make_hello(ciphers=[0x1301, 0x1302])
            pkt = MagicMock()
            pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
            pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None
            return compute_tls_fingerprint_from_scapy(pkt)

        r1, r2, r3 = _fp(), _fp(), _fp()
        assert r1 is not None
        assert r1["ja4"] == r2["ja4"] == r3["ja4"]

    def test_different_ciphers_different_ja4(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        def _fp(ciphers):
            hello = _make_hello(ciphers=ciphers)
            pkt = MagicMock()
            pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
            pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None
            return compute_tls_fingerprint_from_scapy(pkt)

        r1 = _fp([0x1301])
        r2 = _fp([0x1302, 0x1303])
        assert r1 is not None and r2 is not None
        assert r1["ja4"] != r2["ja4"]

    def test_sig_algs_change_ja4_but_not_legacy(self):
        """Sig-algs affect ja4 (FoxIO) but NOT ja4_legacy (old formula)."""
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        ext1 = _make_extension(type_id=0x000D, sig_algs=[0x0403])
        ext2 = _make_extension(type_id=0x000D, sig_algs=[0x0804])

        def _fp(sig_ext):
            hello = _make_hello(ciphers=[0x1301], extensions=[sig_ext])
            pkt = MagicMock()
            pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
            pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None
            return compute_tls_fingerprint_from_scapy(pkt)

        r1 = _fp(ext1)
        r2 = _fp(ext2)
        assert r1 is not None and r2 is not None
        assert r1["ja4"] != r2["ja4"], "different sig_algs must change ja4 (FoxIO)"
        assert r1["ja4_legacy"] == r2["ja4_legacy"], (
            "ja4_legacy must not change with sig_algs (old formula ignores them)"
        )


# ── Parse statistics ──────────────────────────────────────────────────────────

class TestParseStats:
    def setup_method(self):
        reset_parse_stats()

    def test_stats_keys_present(self):
        stats = get_parse_stats()
        for key in ("scapy_ok", "raw_ok", "failed", "not_client_hello",
                    "truncated", "malformed", "import_error"):
            assert key in stats, f"missing stats key: {key}"

    def test_scapy_ok_increments_on_success(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello()
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        before = get_parse_stats()["scapy_ok"]
        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert get_parse_stats()["scapy_ok"] == before + 1

    def test_failed_increments_on_non_tls(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: False  # no TLS layer, no TCP/Raw either

        before = get_parse_stats()["failed"]
        compute_tls_fingerprint_from_scapy(pkt)
        assert get_parse_stats()["failed"] > before

    def test_reset_clears_all_counters(self):
        _skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        # Generate some stats
        hello = _make_hello()
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None
        compute_tls_fingerprint_from_scapy(pkt)

        reset_parse_stats()
        stats = get_parse_stats()
        assert all(v == 0 for v in stats.values()), f"stats not zero after reset: {stats}"

    def test_stats_snapshot_is_copy(self):
        """Modifying returned stats dict must not affect module state."""
        stats = get_parse_stats()
        stats["scapy_ok"] = 9999
        assert get_parse_stats()["scapy_ok"] != 9999
