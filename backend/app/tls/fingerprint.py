"""
Scapy-specific TLS ClientHello parser.

Returns a JA4-LIKE fingerprint dict.

⚠️  NOT official JA4 — simplified custom implementation.
    The "ja4" field name is kept for UI/metadata compatibility.
    The hashing algorithm can be replaced later without changing TLSMonitor.

Public API:
    compute_tls_fingerprint_from_scapy(packet) -> dict | None
    parse_tls_client_hello_raw(data: bytes)    -> dict | None
"""

from __future__ import annotations

import hashlib
import logging

_log = logging.getLogger("app.tls.fingerprint")

# ── GREASE values (RFC 8701) — filtered before hashing ───────────────────────
_GREASE: frozenset[int] = frozenset(
    v for v in range(0x0A0A, 0xFFFF + 1, 0x1010) if (v & 0x0F0F) == 0x0A0A
)

# ── TLS version code mapping ──────────────────────────────────────────────────
_VERSION_CODES: dict[int, str] = {
    0x0301: "10",  # TLS 1.0
    0x0302: "11",  # TLS 1.1
    0x0303: "12",  # TLS 1.2
    0x0304: "13",  # TLS 1.3
}

_VERSION_STRINGS: dict[int, str] = {
    0x0301: "TLS 1.0",
    0x0302: "TLS 1.1",
    0x0303: "TLS 1.2",
    0x0304: "TLS 1.3",
}


def _hex_hash(parts: list[int]) -> str:
    """sha256(sorted hex values joined by comma), first 12 chars."""
    joined = ",".join(f"{v:x}" for v in sorted(parts))
    return hashlib.sha256(joined.encode()).hexdigest()[:12]


def _build_result(
    detected_version: int,
    ciphers: list[int],
    ext_types: list[int],
    sni: str,
    alpn: str,
) -> dict:
    version_code = _VERSION_CODES.get(detected_version, "00")
    cipher_count = len(ciphers)
    ext_count = len(ext_types)
    prefix = f"t{version_code}{cipher_count:02d}{ext_count:02d}"
    cipher_hash = _hex_hash(ciphers) if ciphers else "000000000000"
    ext_hash = _hex_hash(ext_types) if ext_types else "000000000000"
    return {
        "ja4": f"{prefix}_{cipher_hash}_{ext_hash}",
        "sni": sni,
        "alpn": alpn,
        "tls_version": _VERSION_STRINGS.get(detected_version, f"0x{detected_version:04x}"),
        "cipher_count": cipher_count,
        "ext_count": ext_count,
    }


# ── Raw bytes parser ──────────────────────────────────────────────────────────

def parse_tls_client_hello_raw(data: bytes) -> dict | None:
    """Parse TLS ClientHello from raw TCP payload bytes.

    Returns fingerprint dict or None if data is not a valid ClientHello.
    Never raises — all index accesses are guarded.

    Limitation: no TCP reassembly. If the ClientHello is split across
    multiple TCP segments this function returns None (acceptable for MVP).
    """
    # Need at least: 5 (TLS record) + 4 (HS header) + 2 (version) + 32 (random) + 1 (sid_len)
    if len(data) < 44:
        return None

    # ── TLS record header (5 bytes) ───────────────────────────────────────────
    if data[0] != 0x16:          # content_type must be Handshake
        return None
    if data[1] != 0x03:          # major version must be 3 (all TLS 1.x)
        return None
    record_len = (data[3] << 8) | data[4]
    if len(data) < 5 + record_len:   # record split across TCP segments
        return None

    # ── Handshake header (4 bytes at offset 5) ────────────────────────────────
    if data[5] != 0x01:          # handshake_type must be ClientHello
        return None
    hs_len = (data[6] << 16) | (data[7] << 8) | data[8]
    hs_end = 9 + hs_len
    if len(data) < hs_end:
        return None

    pos = 9  # ClientHello body begins here

    # ── client_version (2 bytes) ──────────────────────────────────────────────
    if pos + 2 > hs_end:
        return None
    client_version = (data[pos] << 8) | data[pos + 1]
    pos += 2

    # ── random (32 bytes) ─────────────────────────────────────────────────────
    pos += 32
    if pos > hs_end:
        return None

    # ── session_id ────────────────────────────────────────────────────────────
    if pos + 1 > hs_end:
        return None
    sid_len = data[pos]
    pos += 1 + sid_len
    if pos > hs_end:
        return None

    # ── cipher_suites ─────────────────────────────────────────────────────────
    if pos + 2 > hs_end:
        return None
    cs_len = (data[pos] << 8) | data[pos + 1]
    pos += 2
    if pos + cs_len > hs_end:
        return None
    ciphers: list[int] = []
    cs_end = pos + cs_len
    while pos + 2 <= cs_end:
        c = (data[pos] << 8) | data[pos + 1]
        if c not in _GREASE:
            ciphers.append(c)
        pos += 2
    pos = cs_end

    # ── compression_methods ───────────────────────────────────────────────────
    if pos + 1 > hs_end:
        return None
    comp_len = data[pos]
    pos += 1 + comp_len
    if pos > hs_end:
        return None

    # ── extensions (optional) ─────────────────────────────────────────────────
    ext_types: list[int] = []
    sni = ""
    alpn = ""
    detected_version = client_version

    if pos + 2 <= hs_end:
        exts_len = (data[pos] << 8) | data[pos + 1]
        pos += 2
        exts_end = min(pos + exts_len, hs_end)

        while pos + 4 <= exts_end:
            ext_type = (data[pos] << 8) | data[pos + 1]
            ext_dlen = (data[pos + 2] << 8) | data[pos + 3]
            pos += 4
            ext_data_end = pos + ext_dlen
            if ext_data_end > exts_end:
                break  # truncated extension — stop parsing

            if ext_type not in _GREASE:
                ext_types.append(ext_type)

                # SNI (type 0): [0:2] list_len, [2] name_type, [3:5] name_len, [5:] name
                if ext_type == 0 and ext_dlen >= 5 and pos + 5 <= ext_data_end:
                    if data[pos + 2] == 0x00:  # name_type host_name
                        name_len = (data[pos + 3] << 8) | data[pos + 4]
                        name_end = pos + 5 + name_len
                        if name_end <= ext_data_end:
                            try:
                                sni = data[pos + 5:name_end].decode("ascii", errors="replace")
                            except Exception:
                                pass

                # ALPN (type 16): [0:2] list_len, [2] proto_len, [3:] proto
                elif ext_type == 16 and ext_dlen >= 3 and pos + 3 <= ext_data_end:
                    proto_len = data[pos + 2]
                    proto_end = pos + 3 + proto_len
                    if proto_end <= ext_data_end:
                        try:
                            alpn = data[pos + 3:proto_end].decode("ascii", errors="replace")
                        except Exception:
                            pass

                # Supported Versions (type 43): [0] list_len, [1:] versions (uint16 each)
                # Reveals TLS 1.3 even when outer version field says 0x0303
                elif ext_type == 43 and ext_dlen >= 3 and pos + 1 <= ext_data_end:
                    sv_list_len = data[pos]
                    sv_pos = pos + 1
                    sv_end = sv_pos + sv_list_len
                    if sv_end <= ext_data_end:
                        while sv_pos + 2 <= sv_end:
                            v = (data[sv_pos] << 8) | data[sv_pos + 1]
                            if v == 0x0304:
                                detected_version = 0x0304
                                break
                            sv_pos += 2

            pos = ext_data_end

    return _build_result(detected_version, ciphers, ext_types, sni, alpn)


# ── Scapy-based parser (primary path) ────────────────────────────────────────

def compute_tls_fingerprint_from_scapy(packet) -> dict | None:
    """Extract TLS ClientHello fingerprint from a Scapy packet.

    Two-path dissection:
    1. Native: packet already has TLSClientHello layer (session=SSLSession active).
    2. Raw fallback: packet has TCP/Raw layers — parse bytes directly.
       Works without session= in AsyncSniffer. No TCP reassembly (see above).

    Returns None if packet is not a ClientHello or on any error.
    Never raises.
    """
    # ── Path 1: scapy already dissected TLS ──────────────────────────────────
    try:
        from scapy.layers.tls.handshake import TLSClientHello  # type: ignore[import]
    except ImportError:
        # scapy TLS layer not available — go straight to raw fallback
        TLSClientHello = None  # type: ignore[assignment,misc]

    try:
        if TLSClientHello is not None and packet.haslayer(TLSClientHello):
            hello = packet[TLSClientHello]
            raw_version: int = getattr(hello, "version", 0x0303)
            ciphers_raw = getattr(hello, "ciphers", None) or []
            ciphers: list[int] = [c for c in ciphers_raw if c not in _GREASE]
            exts_raw = getattr(hello, "ext", None) or []
            ext_types: list[int] = []
            sni = ""
            alpn = ""
            for ext in exts_raw:
                ext_type_val: int = getattr(ext, "type", -1)
                if ext_type_val in _GREASE:
                    continue
                ext_types.append(ext_type_val)
                if ext_type_val == 0:
                    try:
                        server_names = getattr(ext, "servernames", [])
                        if server_names:
                            nb = getattr(server_names[0], "servername", b"")
                            sni = nb.decode("ascii", errors="replace") if isinstance(nb, bytes) else str(nb)
                    except Exception:
                        pass
                elif ext_type_val == 16:
                    try:
                        protocols = getattr(ext, "protocols", [])
                        if protocols:
                            pb = getattr(protocols[0], "protocol", b"")
                            alpn = pb.decode("ascii", errors="replace") if isinstance(pb, bytes) else str(pb)
                    except Exception:
                        pass
            return _build_result(raw_version, ciphers, ext_types, sni, alpn)
    except Exception as exc:
        _log.warning("[TLS] scapy dissect error: %s", exc)

    # ── Path 2: raw bytes fallback ────────────────────────────────────────────
    try:
        if not packet.haslayer("TCP") or not packet.haslayer("Raw"):
            return None
        raw_bytes = bytes(packet["Raw"].load)
        return parse_tls_client_hello_raw(raw_bytes)
    except Exception as exc:
        _log.warning("[TLS] raw fallback error: %s", exc)
        return None
