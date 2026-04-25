"""
Scapy-specific TLS ClientHello parser.

Returns a JA4-LIKE fingerprint dict.

⚠️  NOT official JA4 — simplified custom implementation.
    The "ja4" field name is kept for UI/metadata compatibility.
    The hashing algorithm can be replaced later without changing TLSMonitor.

Public API (Scapy-specific):
    compute_tls_fingerprint_from_scapy(packet) -> dict | None
"""

from __future__ import annotations

import hashlib
import logging

_log = logging.getLogger("app.tls.fingerprint")

# ── GREASE values (RFC 8701) — must be filtered out ──────────────────────────
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


def _hex_hash(parts: list[int]) -> str:
    """Return first 12 hex chars of sha256 over comma-joined sorted hex values."""
    joined = ",".join(f"{v:x}" for v in sorted(parts))
    return hashlib.sha256(joined.encode()).hexdigest()[:12]


def compute_tls_fingerprint_from_scapy(packet) -> dict | None:
    """Extract TLS ClientHello fingerprint from a Scapy packet.

    Returns None if packet is not a TLS ClientHello or on any parse error.
    Never raises — all exceptions are caught and logged at WARNING level.
    """
    try:
        from scapy.layers.tls.handshake import TLSClientHello  # type: ignore[import]
    except ImportError:
        return None  # scapy TLS layer not available

    try:
        if not packet.haslayer(TLSClientHello):
            return None

        hello = packet[TLSClientHello]

        # ── TLS version ───────────────────────────────────────────────────────
        raw_version: int = getattr(hello, "version", 0x0303)
        # In TLS 1.3 the outer version is 0x0303 but supported_versions ext contains 0x0304
        version_code = _VERSION_CODES.get(raw_version, "00")

        # ── Cipher suites (filter GREASE) ─────────────────────────────────────
        ciphers_raw = getattr(hello, "ciphers", None) or []
        ciphers: list[int] = [c for c in ciphers_raw if c not in _GREASE]

        # ── Extensions ───────────────────────────────────────────────────────
        exts_raw = getattr(hello, "ext", None) or []
        ext_types: list[int] = []
        sni: str = ""
        alpn: str = ""

        for ext in exts_raw:
            ext_type: int = getattr(ext, "type", -1)
            if ext_type in _GREASE:
                continue
            ext_types.append(ext_type)

            # SNI — extension type 0
            if ext_type == 0:
                try:
                    server_names = getattr(ext, "servernames", [])
                    if server_names:
                        name_bytes = getattr(server_names[0], "servername", b"")
                        sni = (name_bytes.decode("ascii", errors="replace")
                               if isinstance(name_bytes, bytes) else str(name_bytes))
                except Exception:
                    pass

            # ALPN — extension type 16
            elif ext_type == 16:
                try:
                    protocols = getattr(ext, "protocols", [])
                    if protocols:
                        proto_name = getattr(protocols[0], "protocol", b"")
                        alpn = (proto_name.decode("ascii", errors="replace")
                                if isinstance(proto_name, bytes) else str(proto_name))
                except Exception:
                    pass

        # ── Build fingerprint ─────────────────────────────────────────────────
        cipher_count = len(ciphers)
        ext_count = len(ext_types)

        prefix = f"t{version_code}{cipher_count:02d}{ext_count:02d}"
        cipher_hash = _hex_hash(ciphers) if ciphers else "000000000000"
        ext_hash = _hex_hash(ext_types) if ext_types else "000000000000"
        ja4 = f"{prefix}_{cipher_hash}_{ext_hash}"

        return {
            "ja4": ja4,
            "sni": sni,
            "alpn": alpn,
            "tls_version": f"TLS 1.{int(version_code) - 9}" if version_code.isdigit() else "unknown",
            "cipher_count": cipher_count,
            "ext_count": ext_count,
        }

    except Exception as exc:
        _log.warning("[TLS] fingerprint parse error: %s", exc)
        return None
