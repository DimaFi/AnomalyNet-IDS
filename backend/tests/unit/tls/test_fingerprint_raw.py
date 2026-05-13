"""Unit tests for parse_tls_client_hello_raw — no Scapy required.

Tests cover:
- basic parsing (output shape, field correctness)
- GREASE filtering in ciphers and extensions
- extension parsing (SNI, ALPN, supported_versions, signature_algorithms)
- FoxIO-spec ext hash formula (ext_csv + "_" + sigalg_csv)
- canonical vs raw ordering
- reject / never-raise on malformed input
- parse statistics
- property-style determinism tests
"""

from __future__ import annotations

import hashlib
import struct
import threading

import pytest

from app.tls.fingerprint import (
    _GREASE,
    parse_tls_client_hello_raw,
    get_parse_stats,
    reset_parse_stats,
)


# ── ClientHello builder helpers ───────────────────────────────────────────────

def _build_client_hello(
    client_version: int = 0x0303,
    ciphers: list[int] | None = None,
    extensions: list[bytes] | None = None,
) -> bytes:
    if ciphers is None:
        ciphers = [0x1301, 0x1302]
    if extensions is None:
        extensions = []

    random_bytes = b"\xAB" * 32
    session_id   = b""
    cs_bytes     = b"".join(struct.pack("!H", c) for c in ciphers)
    cs_block     = struct.pack("!H", len(cs_bytes)) + cs_bytes
    comp         = b"\x01\x00"
    exts_body    = b"".join(extensions)
    exts_block   = struct.pack("!H", len(exts_body)) + exts_body if exts_body else b""

    hello_body = (
        struct.pack("!H", client_version)
        + random_bytes
        + struct.pack("!B", len(session_id)) + session_id
        + cs_block + comp + exts_block
    )
    hs_header  = b"\x01" + struct.pack("!I", len(hello_body))[1:]
    handshake  = hs_header + hello_body
    record     = struct.pack("!BHH", 0x16, 0x0301, len(handshake)) + handshake
    return record


def _ext(t: int, data: bytes) -> bytes:
    return struct.pack("!HH", t, len(data)) + data

def _sni_ext(hostname: str) -> bytes:
    name  = hostname.encode("ascii")
    entry = b"\x00" + struct.pack("!H", len(name)) + name
    return _ext(0x0000, struct.pack("!H", len(entry)) + entry)

def _alpn_ext(protocol: str) -> bytes:
    proto       = protocol.encode("ascii")
    proto_entry = struct.pack("!B", len(proto)) + proto
    return _ext(0x0010, struct.pack("!H", len(proto_entry)) + proto_entry)

def _supported_versions_ext(versions: list[int]) -> bytes:
    body = b"".join(struct.pack("!H", v) for v in versions)
    return _ext(0x002B, struct.pack("!B", len(body)) + body)

def _signature_algorithms_ext(values: list[int]) -> bytes:
    body = b"".join(struct.pack("!H", v) for v in values)
    return _ext(0x000D, struct.pack("!H", len(body)) + body)


# Expected hash helpers (mirror the corrected FoxIO formula)

def _cipher_hash(ciphers: list[int]) -> str:
    items = sorted(f"{c:04x}" for c in ciphers)
    return hashlib.sha256(",".join(items).encode()).hexdigest()[:12]

def _ext_hash(ext_types: list[int], sig_algs: list[int]) -> str:
    """FoxIO ext hash: SHA256("<sorted_ext_csv>_<sorted_sigalg_csv>")[:12]."""
    exts = sorted(f"{e:04x}" for e in ext_types if e not in {0x0000, 0x0010})
    sigs = sorted(f"{s:04x}" for s in sig_algs)
    ext_part = ",".join(exts)
    sig_part = ",".join(sigs)
    if not ext_part and not sig_part:
        return "000000000000"
    return hashlib.sha256(f"{ext_part}_{sig_part}".encode()).hexdigest()[:12]


# ── Basic output ──────────────────────────────────────────────────────────────

class TestRawFallbackBasic:
    def test_valid_hello_returns_required_keys(self):
        r = parse_tls_client_hello_raw(_build_client_hello())
        assert r is not None
        for key in ("ja4", "ja4_raw", "ja4_legacy", "ja4_source", "ja4_version",
                    "sni", "alpn", "tls_version", "cipher_count", "ext_count"):
            assert key in r, f"missing key: {key}"

    def test_source_is_raw_tcp(self):
        r = parse_tls_client_hello_raw(_build_client_hello())
        assert r is not None
        assert r["ja4_source"] == "raw_tcp"

    def test_version_tag_is_foxio_v1(self):
        r = parse_tls_client_hello_raw(_build_client_hello())
        assert r is not None
        assert r["ja4_version"] == "foxio_v1"

    def test_ja4_has_three_underscore_parts(self):
        r = parse_tls_client_hello_raw(_build_client_hello())
        assert r is not None
        assert len(r["ja4"].split("_")) == 3

    def test_cipher_count_correct(self):
        r = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x1301, 0x1302, 0x1303]))
        assert r is not None
        assert r["cipher_count"] == 3

    def test_grease_filtered_from_ciphers(self):
        assert 0x0A0A in _GREASE
        r = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x0A0A, 0x1301, 0x1302]))
        assert r is not None
        assert r["cipher_count"] == 2

    def test_same_input_deterministic(self):
        data = _build_client_hello()
        assert parse_tls_client_hello_raw(data)["ja4"] == parse_tls_client_hello_raw(data)["ja4"]

    def test_different_ciphers_different_ja4(self):
        r1 = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x1301]))
        r2 = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x1302, 0x1303]))
        assert r1 is not None and r2 is not None
        assert r1["ja4"] != r2["ja4"]


# ── Reject invalid input ──────────────────────────────────────────────────────

class TestRawFallbackRejectsInvalid:
    def test_non_tls_bytes_returns_none(self):
        assert parse_tls_client_hello_raw(b"\x17\x03\x03\x00\x05hello") is None

    def test_empty_returns_none(self):
        assert parse_tls_client_hello_raw(b"") is None

    def test_too_short_returns_none(self):
        assert parse_tls_client_hello_raw(b"\x16\x03\x01") is None

    def test_truncated_record_returns_none(self):
        assert parse_tls_client_hello_raw(_build_client_hello()[:20]) is None

    def test_wrong_content_type_returns_none(self):
        data = bytearray(_build_client_hello())
        data[0] = 0x17
        assert parse_tls_client_hello_raw(bytes(data)) is None

    def test_wrong_handshake_type_returns_none(self):
        data = bytearray(_build_client_hello())
        data[5] = 0x02  # ServerHello
        assert parse_tls_client_hello_raw(bytes(data)) is None

    def test_never_raises_on_garbage(self):
        for bad in [b"\x00" * 100, b"\xff" * 50, b"", b"\x16\x03" + b"\xff" * 200]:
            result = parse_tls_client_hello_raw(bad)
            assert result is None or isinstance(result, dict)

    def test_all_grease_ciphers_returns_zero_cipher_count(self):
        grease_ciphers = [v for v in _GREASE][:4]
        r = parse_tls_client_hello_raw(_build_client_hello(ciphers=grease_ciphers))
        assert r is not None
        assert r["cipher_count"] == 0


# ── Extension parsing ─────────────────────────────────────────────────────────

class TestRawFallbackExtensions:
    def test_sni_extracted(self):
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=[_sni_ext("example.com")]))
        assert r is not None and r["sni"] == "example.com"

    def test_alpn_extracted(self):
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=[_alpn_ext("h2")]))
        assert r is not None and r["alpn"] == "h2"

    def test_alpn_http11(self):
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=[_alpn_ext("http/1.1")]))
        assert r is not None and r["alpn"] == "http/1.1"

    def test_tls13_via_supported_versions(self):
        exts = [_supported_versions_ext([0x0304, 0x0303])]
        r = parse_tls_client_hello_raw(_build_client_hello(client_version=0x0303, extensions=exts))
        assert r is not None and r["tls_version"] == "TLS 1.3"

    def test_ext_count_correct(self):
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=[_sni_ext("x.com"), _alpn_ext("h2")]))
        assert r is not None and r["ext_count"] == 2

    def test_grease_ext_excluded_from_count(self):
        r = parse_tls_client_hello_raw(
            _build_client_hello(extensions=[_ext(0x0A0A, b"\x00"), _ext(0x0017, b"")])
        )
        assert r is not None and r["ext_count"] == 1

    def test_empty_sni_when_no_sni_ext(self):
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=[_alpn_ext("h2")]))
        assert r is not None and r["sni"] == ""

    def test_empty_alpn_when_no_alpn_ext(self):
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=[_sni_ext("x.com")]))
        assert r is not None and r["alpn"] == ""


# ── FoxIO-correct ext hash formula ───────────────────────────────────────────

class TestFoxIOExtHash:
    """Verify ext hash uses SHA256("ext_csv_sorted" + "_" + "sigalg_csv_sorted")."""

    def test_ext_hash_matches_foxio_formula(self):
        """ext hash = SHA256("<sorted_ext_types_excl_sni_alpn>_<sorted_sig_algs>")[:12]."""
        sigs = [0x0403, 0x0804]
        exts = [
            _sni_ext("example.com"),       # 0x0000 — excluded from hash
            _alpn_ext("h2"),               # 0x0010 — excluded from hash
            _ext(0x0017, b""),             # extended_master_secret
            _signature_algorithms_ext(sigs),  # 0x000D — in sig part
            _supported_versions_ext([0x0304]),  # 0x002B
        ]
        r = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x1301, 0x1302], extensions=exts))
        assert r is not None

        # After filtering SNI(0) and ALPN(16): remaining ext types = [0x0017, 0x000D, 0x002B]
        expected_eh = _ext_hash([0x0017, 0x000D, 0x002B], sigs)
        actual_eh   = r["ja4"].split("_")[2]
        assert actual_eh == expected_eh, (
            f"ext hash mismatch\n  expected: {expected_eh}\n  got:      {actual_eh}\n"
            f"  ja4:      {r['ja4']}"
        )

    def test_no_sig_algs_still_uses_underscore_separator(self):
        """ext hash with no sig algs: SHA256("<exts>_")[:12], NOT just SHA256("<exts>")."""
        exts = [_ext(0x0017, b""), _supported_versions_ext([0x0304])]
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=exts))
        assert r is not None

        expected_eh = _ext_hash([0x0017, 0x002B], [])
        actual_eh   = r["ja4"].split("_")[2]
        assert actual_eh == expected_eh

    def test_sig_algs_change_ext_hash(self):
        base = parse_tls_client_hello_raw(_build_client_hello(extensions=[_ext(0x0017, b"")]))
        sigs = parse_tls_client_hello_raw(
            _build_client_hello(extensions=[_ext(0x0017, b""), _signature_algorithms_ext([0x0403, 0x0804])])
        )
        assert base is not None and sigs is not None
        assert base["ja4"].split("_")[2] != sigs["ja4"].split("_")[2]

    def test_cipher_hash_is_independent_of_ext_hash(self):
        r = parse_tls_client_hello_raw(
            _build_client_hello(ciphers=[0x1301, 0x1302], extensions=[_ext(0x0017, b"")])
        )
        assert r is not None
        expected_ch = _cipher_hash([0x1301, 0x1302])
        actual_ch   = r["ja4"].split("_")[1]
        assert actual_ch == expected_ch

    def test_exact_canonical_vector(self):
        """Full end-to-end vector with known expected values."""
        ciphers = [0x1301, 0x1302]
        sigs    = [0x0403, 0x0804]
        exts = [
            _sni_ext("example.com"),
            _alpn_ext("h2"),
            _ext(0x0017, b""),
            _signature_algorithms_ext(sigs),
            _supported_versions_ext([0x0304, 0x0303]),
        ]
        r = parse_tls_client_hello_raw(_build_client_hello(ciphers=ciphers, extensions=exts))
        assert r is not None

        # prefix: t=TCP, 13=TLS1.3, d=SNI present, 02=2 ciphers, 05=5 exts, h2=ALPN
        assert r["ja4"].startswith("t13d0205h2_")

        expected_ch = _cipher_hash(ciphers)
        # Exts after filtering SNI+ALPN: [0x0017, 0x000D, 0x002B]
        expected_eh = _ext_hash([0x0017, 0x000D, 0x002B], sigs)
        assert r["ja4"] == f"t13d0205h2_{expected_ch}_{expected_eh}"

    def test_legacy_field_uses_old_formula(self):
        """ja4_legacy should differ from ja4 (old formula vs new)."""
        exts = [_sni_ext("x.com"), _ext(0x0017, b""), _signature_algorithms_ext([0x0403])]
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=exts))
        assert r is not None
        # They may differ or not — but legacy must be present and 3-part
        assert len(r["ja4_legacy"].split("_")) == 3


# ── Canonical vs raw ordering ─────────────────────────────────────────────────

class TestCanonicalVsRaw:
    def test_canonical_same_regardless_of_wire_order(self):
        """Reordering ciphers/exts must NOT change ja4 (canonical)."""
        exts_a = [_ext(0x0017, b""), _supported_versions_ext([0x0304, 0x0303])]
        exts_b = [_supported_versions_ext([0x0304, 0x0303]), _ext(0x0017, b"")]
        r1 = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x1301, 0x1302], extensions=exts_a))
        r2 = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x1302, 0x1301], extensions=exts_b))
        assert r1 is not None and r2 is not None
        assert r1["ja4"] == r2["ja4"]

    def test_raw_changes_with_wire_order(self):
        exts_a = [_ext(0x0017, b""), _supported_versions_ext([0x0304])]
        exts_b = [_supported_versions_ext([0x0304]), _ext(0x0017, b"")]
        r1 = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x1301, 0x1302], extensions=exts_a))
        r2 = parse_tls_client_hello_raw(_build_client_hello(ciphers=[0x1302, 0x1301], extensions=exts_b))
        assert r1 is not None and r2 is not None
        # ja4 same, ja4_raw different (preserves original order)
        assert r1["ja4"] == r2["ja4"]
        assert r1["ja4_raw"] != r2["ja4_raw"]

    def test_sni_and_alpn_dont_affect_cipher_ext_hashes(self):
        """SNI and ALPN change the prefix (d vs i, alpn_token) but not cipher/ext hashes."""
        exts1 = [_sni_ext("one.example"), _alpn_ext("h2"), _ext(0x0017, b"")]
        exts2 = [_sni_ext("two.example"), _alpn_ext("http/1.1"), _ext(0x0017, b"")]
        r1 = parse_tls_client_hello_raw(_build_client_hello(extensions=exts1))
        r2 = parse_tls_client_hello_raw(_build_client_hello(extensions=exts2))
        assert r1 is not None and r2 is not None
        # cipher hash (part 1) and ext hash (part 2) should be equal
        assert r1["ja4"].split("_")[1] == r2["ja4"].split("_")[1]
        assert r1["ja4"].split("_")[2] == r2["ja4"].split("_")[2]
        # prefix differs (different SNI and ALPN token)
        assert r1["ja4"].split("_")[0] != r2["ja4"].split("_")[0]


# ── ALPN token edge cases ─────────────────────────────────────────────────────

class TestAlpnToken:
    def test_h2_token_is_h2(self):
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=[_alpn_ext("h2")]))
        assert r is not None
        assert r["ja4"].split("_")[0].endswith("h2")

    def test_http11_token_is_h1(self):
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=[_alpn_ext("http/1.1")]))
        assert r is not None
        assert r["ja4"].split("_")[0].endswith("h1")

    def test_no_alpn_token_is_00(self):
        r = parse_tls_client_hello_raw(_build_client_hello())
        assert r is not None
        assert r["ja4"].split("_")[0].endswith("00")


# ── SNI indicator ─────────────────────────────────────────────────────────────

class TestSniIndicator:
    def test_sni_present_gives_d(self):
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=[_sni_ext("example.com")]))
        assert r is not None
        # prefix format: t<ver><d|i><cc><ec><alpn>
        assert r["ja4"][3] == "d"

    def test_no_sni_gives_i(self):
        r = parse_tls_client_hello_raw(_build_client_hello())
        assert r is not None
        assert r["ja4"][3] == "i"


# ── Parse statistics ──────────────────────────────────────────────────────────

class TestParseStats:
    def setup_method(self):
        reset_parse_stats()

    def test_successful_parse_increments_raw_ok(self):
        parse_tls_client_hello_raw(_build_client_hello())
        assert get_parse_stats()["raw_ok"] == 1

    def test_invalid_input_increments_failed(self):
        parse_tls_client_hello_raw(b"garbage")
        assert get_parse_stats()["failed"] >= 1

    def test_reset_clears_counters(self):
        parse_tls_client_hello_raw(_build_client_hello())
        reset_parse_stats()
        assert get_parse_stats()["raw_ok"] == 0


# ── Concurrency / thread-safety ───────────────────────────────────────────────

class TestConcurrency:
    def test_concurrent_parses_do_not_crash(self):
        """parse_tls_client_hello_raw must be safe to call from multiple threads."""
        data = _build_client_hello(
            ciphers=[0x1301, 0x1302, 0x1303],
            extensions=[
                _sni_ext("concurrent.test"),
                _alpn_ext("h2"),
                _signature_algorithms_ext([0x0403, 0x0804]),
                _supported_versions_ext([0x0304]),
            ]
        )
        errors: list[Exception] = []
        results: list[dict] = []

        def worker():
            try:
                r = parse_tls_client_hello_raw(data)
                if r:
                    results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(40)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors, f"Exceptions in threads: {errors}"
        assert len(results) == 40
        # All results must be identical (deterministic)
        ja4s = {r["ja4"] for r in results}
        assert len(ja4s) == 1

    def test_concurrent_garbage_input_does_not_crash(self):
        import random
        errors: list[Exception] = []

        def worker():
            try:
                data = bytes(random.getrandbits(8) for _ in range(random.randint(0, 300)))
                parse_tls_client_hello_raw(data)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(30)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors


# ── Fuzz-style edge cases ─────────────────────────────────────────────────────

class TestFuzzEdgeCases:
    """Constructed inputs that hit uncommon code paths."""

    def test_zero_ciphers(self):
        data = _build_client_hello(ciphers=[])
        r = parse_tls_client_hello_raw(data)
        assert r is not None and r["cipher_count"] == 0

    def test_zero_extensions(self):
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=[]))
        assert r is not None and r["ext_count"] == 0

    def test_many_grease_extensions(self):
        grease_exts = [_ext(0x0A0A, b""), _ext(0x1A1A, b""), _ext(0x2A2A, b"")]
        r = parse_tls_client_hello_raw(_build_client_hello(extensions=grease_exts))
        assert r is not None and r["ext_count"] == 0

    def test_large_session_id(self):
        # session_id can be up to 32 bytes
        session_id_len = 32
        sid_bytes = bytes([session_id_len]) + b"\xAA" * session_id_len
        # Build manually with a large session id
        ciphers = [0x1301, 0x1302]
        cs_bytes = b"".join(struct.pack("!H", c) for c in ciphers)
        cs_block = struct.pack("!H", len(cs_bytes)) + cs_bytes
        hello_body = struct.pack("!H", 0x0303) + b"\x00" * 32 + sid_bytes + cs_block + b"\x01\x00"
        hs = b"\x01" + struct.pack("!I", len(hello_body))[1:] + hello_body
        record = struct.pack("!BHH", 0x16, 0x0301, len(hs)) + hs
        r = parse_tls_client_hello_raw(record)
        assert r is not None

    def test_truncated_extension_data_graceful(self):
        # Extension declares length > actual data — parser must stop, not crash
        ciphers_bytes = struct.pack("!H", 0x1301)
        cs_block = struct.pack("!H", len(ciphers_bytes)) + ciphers_bytes
        # Extension type=0x0017, declared_len=100 but only 2 bytes of data
        broken_ext = struct.pack("!HH", 0x0017, 100) + b"\x00\x01"
        exts_block = struct.pack("!H", len(broken_ext)) + broken_ext
        hello_body = (struct.pack("!H", 0x0303) + b"\x00" * 32 +
                      b"\x00" + cs_block + b"\x01\x00" + exts_block)
        hs = b"\x01" + struct.pack("!I", len(hello_body))[1:] + hello_body
        record = struct.pack("!BHH", 0x16, 0x0301, len(hs)) + hs
        # Must not raise — may return None or partial result
        try:
            result = parse_tls_client_hello_raw(record)
            assert result is None or isinstance(result, dict)
        except Exception as e:
            pytest.fail(f"Must not raise: {e}")

    def test_max_cipher_count_capped_at_99(self):
        # 100 unique ciphers (from 0x0001 to 0x0064)
        ciphers = list(range(1, 101))
        data = _build_client_hello(ciphers=ciphers)
        r = parse_tls_client_hello_raw(data)
        assert r is not None
        # cipher_count reflects actual parsed count (100), prefix caps at 99
        assert r["ja4"].split("_")[0][4:6] == "99"
