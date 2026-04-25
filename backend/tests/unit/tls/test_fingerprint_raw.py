"""Unit tests for parse_tls_client_hello_raw — no Scapy required."""
import struct
import pytest

from app.tls.fingerprint import parse_tls_client_hello_raw, _GREASE


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_client_hello(
    client_version: int = 0x0303,
    ciphers: list[int] | None = None,
    extensions: list[bytes] | None = None,
) -> bytes:
    """Build a minimal but structurally valid TLS ClientHello record."""
    if ciphers is None:
        ciphers = [0x1301, 0x1302]
    if extensions is None:
        extensions = []

    random_bytes = b"\xAB" * 32
    session_id = b""  # empty

    cs_bytes = b"".join(struct.pack("!H", c) for c in ciphers)
    cs_block = struct.pack("!H", len(cs_bytes)) + cs_bytes

    comp = b"\x01\x00"  # 1 method: null

    exts_body = b"".join(extensions)
    exts_block = struct.pack("!H", len(exts_body)) + exts_body if exts_body else b""

    hello_body = (
        struct.pack("!H", client_version)
        + random_bytes
        + struct.pack("!B", len(session_id)) + session_id
        + cs_block
        + comp
        + exts_block
    )

    hs_header = b"\x01" + struct.pack("!I", len(hello_body))[1:]  # 3-byte length
    handshake = hs_header + hello_body

    record_version = 0x0301  # TLS 1.0 on the wire (always)
    record = struct.pack("!BHH", 0x16, record_version, len(handshake)) + handshake
    return record


def _ext(ext_type: int, data: bytes) -> bytes:
    """Build a TLS extension: type(2) + length(2) + data."""
    return struct.pack("!HH", ext_type, len(data)) + data


def _sni_ext(hostname: str) -> bytes:
    name = hostname.encode("ascii")
    # name_type(1) + name_len(2) + name
    entry = b"\x00" + struct.pack("!H", len(name)) + name
    # list_len(2) + entry
    return _ext(0, struct.pack("!H", len(entry)) + entry)


def _alpn_ext(protocol: str) -> bytes:
    proto = protocol.encode("ascii")
    # proto_len(1) + proto
    proto_entry = struct.pack("!B", len(proto)) + proto
    # list_len(2) + proto_entry
    return _ext(16, struct.pack("!H", len(proto_entry)) + proto_entry)


def _supported_versions_ext(versions: list[int]) -> bytes:
    body = b"".join(struct.pack("!H", v) for v in versions)
    return _ext(43, struct.pack("!B", len(body)) + body)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRawFallbackBasic:
    def test_valid_hello_returns_dict(self):
        data = _build_client_hello()
        result = parse_tls_client_hello_raw(data)
        assert result is not None
        for key in ("ja4", "sni", "alpn", "tls_version", "cipher_count", "ext_count"):
            assert key in result

    def test_cipher_count_correct(self):
        data = _build_client_hello(ciphers=[0x1301, 0x1302, 0x1303])
        result = parse_tls_client_hello_raw(data)
        assert result is not None
        assert result["cipher_count"] == 3

    def test_grease_filtered_from_ciphers(self):
        grease = 0x0A0A
        assert grease in _GREASE
        data = _build_client_hello(ciphers=[grease, 0x1301, 0x1302])
        result = parse_tls_client_hello_raw(data)
        assert result is not None
        assert result["cipher_count"] == 2  # GREASE excluded

    def test_ja4_has_three_parts(self):
        data = _build_client_hello()
        result = parse_tls_client_hello_raw(data)
        assert result is not None
        parts = result["ja4"].split("_")
        assert len(parts) == 3

    def test_same_input_deterministic(self):
        data = _build_client_hello(ciphers=[0x1301, 0x1302])
        assert parse_tls_client_hello_raw(data)["ja4"] == parse_tls_client_hello_raw(data)["ja4"]

    def test_different_ciphers_different_ja4(self):
        r1 = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x1301]))
        r2 = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x1302, 0x1303]))
        assert r1 is not None and r2 is not None
        assert r1["ja4"] != r2["ja4"]


class TestRawFallbackRejectsInvalid:
    def test_non_tls_bytes_returns_none(self):
        assert parse_tls_client_hello_raw(b"\x17\x03\x03\x00\x05hello") is None

    def test_too_short_returns_none(self):
        assert parse_tls_client_hello_raw(b"\x16\x03\x01") is None

    def test_empty_returns_none(self):
        assert parse_tls_client_hello_raw(b"") is None

    def test_truncated_record_returns_none(self):
        data = _build_client_hello()
        assert parse_tls_client_hello_raw(data[:20]) is None

    def test_wrong_content_type_returns_none(self):
        data = bytearray(_build_client_hello())
        data[0] = 0x17  # ApplicationData, not Handshake
        assert parse_tls_client_hello_raw(bytes(data)) is None

    def test_wrong_handshake_type_returns_none(self):
        data = bytearray(_build_client_hello())
        data[5] = 0x02  # ServerHello, not ClientHello
        assert parse_tls_client_hello_raw(bytes(data)) is None

    def test_never_raises(self):
        for bad in [b"\x00" * 100, b"\xff" * 50, b""]:
            result = parse_tls_client_hello_raw(bad)
            assert result is None or isinstance(result, dict)


class TestRawFallbackExtensions:
    def test_sni_extracted(self):
        exts = [_sni_ext("example.com")]
        data = _build_client_hello(extensions=exts)
        result = parse_tls_client_hello_raw(data)
        assert result is not None
        assert result["sni"] == "example.com"

    def test_alpn_extracted(self):
        exts = [_alpn_ext("h2")]
        data = _build_client_hello(extensions=exts)
        result = parse_tls_client_hello_raw(data)
        assert result is not None
        assert result["alpn"] == "h2"

    def test_tls13_detected_via_supported_versions(self):
        exts = [_supported_versions_ext([0x0304, 0x0303])]
        data = _build_client_hello(client_version=0x0303, extensions=exts)
        result = parse_tls_client_hello_raw(data)
        assert result is not None
        assert result["tls_version"] == "TLS 1.3"

    def test_ext_count_correct(self):
        exts = [_sni_ext("test.com"), _alpn_ext("h2")]
        data = _build_client_hello(extensions=exts)
        result = parse_tls_client_hello_raw(data)
        assert result is not None
        assert result["ext_count"] == 2

    def test_grease_ext_filtered(self):
        grease_ext = _ext(0x0A0A, b"\x00")
        real_ext = _ext(0x0017, b"")  # extended_master_secret
        data = _build_client_hello(extensions=[grease_ext, real_ext])
        result = parse_tls_client_hello_raw(data)
        assert result is not None
        assert result["ext_count"] == 1  # GREASE filtered
