"""Unit tests for app.tls.fingerprint — uses mock Scapy objects, no real packets."""
import pytest
from unittest.mock import MagicMock, patch

from app.tls.fingerprint import compute_tls_fingerprint_from_scapy, _GREASE


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_extension(type_id: int, servername=None, alpn_protocol=None):
    """Create a minimal mock extension object."""
    ext = MagicMock()
    ext.type = type_id
    if servername is not None:
        sn = MagicMock()
        sn.servername = servername
        ext.servernames = [sn]
    else:
        ext.servernames = []
    if alpn_protocol is not None:
        proto = MagicMock()
        proto.protocol = alpn_protocol
        ext.protocols = [proto]
    else:
        ext.protocols = []
    return ext


def _make_hello(version=0x0303, ciphers=None, extensions=None):
    """Create a mock TLSClientHello."""
    hello = MagicMock()
    hello.version = version
    hello.ciphers = ciphers or [0x1301, 0x1302, 0x1303]
    hello.ext = extensions or []
    return hello


def _make_packet(hello):
    """Wrap hello in a mock packet."""
    pkt = MagicMock()

    # Import the real class for isinstance/haslayer checks
    try:
        from scapy.layers.tls.handshake import TLSClientHello
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None
    except ImportError:
        pkt.haslayer.return_value = False

    return pkt


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestNonTlsPacket:
    def test_packet_without_tls_layer_returns_none(self):
        """Packet without TLSClientHello layer → None."""
        try:
            from scapy.layers.tls.handshake import TLSClientHello
        except ImportError:
            pytest.skip("scapy TLS not available")

        pkt = MagicMock()
        pkt.haslayer.return_value = False
        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is None

    def test_exception_during_parse_returns_none(self):
        """Any exception during parsing → None (never raises)."""
        try:
            from scapy.layers.tls.handshake import TLSClientHello
        except ImportError:
            pytest.skip("scapy TLS not available")

        pkt = MagicMock()
        pkt.haslayer.side_effect = RuntimeError("broken packet")
        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is None

    def test_import_error_returns_none(self):
        """If scapy TLS layer is not available → None."""
        with patch.dict("sys.modules", {"scapy.layers.tls.handshake": None}):
            pkt = MagicMock()
            result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is None


class TestFingerprintBasic:
    def setup_method(self):
        try:
            from scapy.layers.tls.handshake import TLSClientHello
            self._tls_available = True
        except ImportError:
            self._tls_available = False

    def _skip_if_no_scapy(self):
        if not self._tls_available:
            pytest.skip("scapy TLS not available")

    def test_returns_dict_with_required_keys(self):
        self._skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello()
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        for key in ("ja4", "sni", "alpn", "tls_version", "cipher_count", "ext_count"):
            assert key in result, f"missing key: {key}"

    def test_ja4_has_underscore_structure(self):
        """JA4-like fingerprint must have two underscores (prefix_ciphers_exts)."""
        self._skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        hello = _make_hello(ciphers=[0x1301, 0x1302])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        parts = result["ja4"].split("_")
        assert len(parts) == 3, f"expected 3 parts, got: {result['ja4']}"

    def test_sni_extracted(self):
        self._skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        sni_ext = _make_extension(type_id=0, servername=b"example.com")
        hello = _make_hello(extensions=[sni_ext])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["sni"] == "example.com"

    def test_alpn_extracted(self):
        self._skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        alpn_ext = _make_extension(type_id=16, alpn_protocol=b"h2")
        hello = _make_hello(extensions=[alpn_ext])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["alpn"] == "h2"

    def test_grease_filtered_from_ciphers(self):
        """GREASE cipher values must not be counted in cipher_count."""
        self._skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        grease_val = 0x0A0A
        real_ciphers = [0x1301, 0x1302]
        hello = _make_hello(ciphers=[grease_val] + real_ciphers)
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["cipher_count"] == len(real_ciphers)

    def test_grease_filtered_from_extensions(self):
        """GREASE extension types must not be counted in ext_count."""
        self._skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        grease_ext = _make_extension(type_id=0x0A0A)
        real_ext = _make_extension(type_id=0x0017)  # extended_master_secret
        hello = _make_hello(extensions=[grease_ext, real_ext])
        pkt = MagicMock()
        pkt.haslayer.side_effect = lambda cls: cls == TLSClientHello
        pkt.__getitem__.side_effect = lambda cls: hello if cls == TLSClientHello else None

        result = compute_tls_fingerprint_from_scapy(pkt)
        assert result is not None
        assert result["ext_count"] == 1

    def test_different_packets_produce_different_ja4(self):
        """Two ClientHellos with different cipher suites must have different ja4."""
        self._skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        def _fp(ciphers):
            h = _make_hello(ciphers=ciphers)
            p = MagicMock()
            p.haslayer.side_effect = lambda cls: cls == TLSClientHello
            p.__getitem__.side_effect = lambda cls: h if cls == TLSClientHello else None
            return compute_tls_fingerprint_from_scapy(p)

        r1 = _fp([0x1301])
        r2 = _fp([0x1302, 0x1303])
        assert r1 is not None and r2 is not None
        assert r1["ja4"] != r2["ja4"]

    def test_same_packet_produces_same_ja4(self):
        """Same cipher suites + extensions → same ja4 (deterministic)."""
        self._skip_if_no_scapy()
        from scapy.layers.tls.handshake import TLSClientHello

        def _fp():
            h = _make_hello(ciphers=[0x1301, 0x1302])
            p = MagicMock()
            p.haslayer.side_effect = lambda cls: cls == TLSClientHello
            p.__getitem__.side_effect = lambda cls: h if cls == TLSClientHello else None
            return compute_tls_fingerprint_from_scapy(p)

        assert _fp()["ja4"] == _fp()["ja4"]
