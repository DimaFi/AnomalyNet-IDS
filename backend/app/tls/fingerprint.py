"""
TLS ClientHello parser — JA4 fingerprinting (FoxIO-compatible).

Two dissection paths:
  1. Scapy native  — packet has TLSClientHello layer (requires SSLSession).
  2. Raw TCP bytes — manual parse from TCP payload (no TCP reassembly).

Public API
----------
compute_tls_fingerprint_from_scapy(packet) -> dict | None
parse_tls_client_hello_raw(data: bytes)    -> dict | None
get_parse_stats()                          -> dict
reset_parse_stats()                        -> None

Output dict keys
----------------
ja4          canonical FoxIO JA4 (sorted ciphers / exts / sig-algs)
ja4_raw      JA4 with original wire order (debug / parity)
ja4_legacy   pre-FoxIO AnomalyNet format (backward compat only)
ja4_source   "scapy_tls" | "raw_tcp"
ja4_version  format version tag — bumped on formula changes
sni          SNI hostname, "" if absent
alpn         first ALPN protocol, "" if absent
tls_version  human-readable TLS version
cipher_count non-GREASE cipher count
ext_count    non-GREASE extension count

JA4 format (FoxIO spec)
-----------------------
  {transport}{tls_version}{sni_flag}{cc:02d}{ec:02d}{alpn_token}
    _ SHA256( sorted_cipher_csv )[:12]
    _ SHA256( sorted_ext_csv + "_" + sorted_sigalg_csv )[:12]

  transport  : t (TCP) | q (QUIC, future)
  tls_version: 13 / 12 / 11 / 10
  sni_flag   : d (SNI present) | i (absent)
  cc / ec    : counts capped at 99, GREASE filtered
  alpn_token : first+last char of first ALPN, or "00"

  cipher hash  = SHA256(",".join(sorted_hex4_ciphers))[:12]
  ext hash     = SHA256(ext_part + "_" + sigalg_part)[:12]
                   ext_part    = ",".join(sorted_hex4_exts)   -- SNI+ALPN excluded
                   sigalg_part = ",".join(sorted_hex4_sigalgs)

IMPORTANT: ja4_legacy uses the old formula (all exts in one hash, no sig-algs)
and exists only for backward-compat with stored events. Do not use for detection.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

_log = logging.getLogger("app.tls.fingerprint")

# ── Constants ─────────────────────────────────────────────────────────────────

_JA4_VERSION  = "foxio_v1"         # bumped from foxio_compat_v1 — ext hash fixed
_JA4_ZERO     = "000000000000"     # 12-char zero hash for empty inputs

# RFC 8701 GREASE values filtered before counting / hashing
_GREASE: frozenset[int] = frozenset(
    v for v in range(0x0A0A, 0xFFFF + 1, 0x1010) if (v & 0x0F0F) == 0x0A0A
)

_VERSION_CODES: dict[int, str] = {
    0x0301: "10", 0x0302: "11", 0x0303: "12", 0x0304: "13",
}
_VERSION_STRINGS: dict[int, str] = {
    0x0301: "TLS 1.0", 0x0302: "TLS 1.1", 0x0303: "TLS 1.2", 0x0304: "TLS 1.3",
}

_EXT_SNI                = 0x0000
_EXT_ALPN               = 0x0010
_EXT_SIGNATURE_ALGS     = 0x000D
_EXT_SUPPORTED_VERSIONS = 0x002B


# ── Parse statistics (module-level, GIL-safe for simple int increments) ───────

@dataclass
class _ParseStats:
    scapy_ok:         int = 0
    raw_ok:           int = 0
    failed:           int = 0
    not_client_hello: int = 0
    truncated:        int = 0
    malformed:        int = 0
    import_error:     int = 0

_stats = _ParseStats()


def get_parse_stats() -> dict:
    """Return a snapshot of module-level parse counters."""
    return {k: getattr(_stats, k) for k in _stats.__dataclass_fields__}


def reset_parse_stats() -> None:
    global _stats
    _stats = _ParseStats()


# ── Hash helpers ──────────────────────────────────────────────────────────────

def _sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _cipher_hash(ciphers: list[int], *, sort: bool) -> str:
    items = [f"{c:04x}" for c in ciphers]
    if sort:
        items.sort()
    return _sha12(",".join(items)) if items else _JA4_ZERO


def _ext_hash(ext_types: list[int], sig_algs: list[int], *, sort: bool) -> str:
    """FoxIO JA4_c formula: SHA256("<sorted_ext_csv>_<sorted_sigalg_csv>")[:12].

    SNI (0x0000) and ALPN (0x0010) are excluded from ext_types.
    The underscore separator is always present, even when one side is empty.
    Both sides empty → zero hash (no extensions at all is degenerate input).
    """
    exts = [e for e in ext_types if e not in {_EXT_SNI, _EXT_ALPN}]
    sigs = list(sig_algs)
    if sort:
        exts.sort()
        sigs.sort()
    ext_part = ",".join(f"{e:04x}" for e in exts)
    sig_part = ",".join(f"{s:04x}" for s in sigs)
    if not ext_part and not sig_part:
        return _JA4_ZERO
    return _sha12(f"{ext_part}_{sig_part}")


def _alpn_token(alpn: str) -> str:
    """JA4 ALPN token: first+last char, "00" if empty or non-ASCII.

    Single-char ALPN: char repeated ("h" → "hh").
    ≥2 chars: first+last ("http/1.1" → "h1", "h2" → "h2").
    """
    if not alpn or ord(alpn[0]) > 127:
        return "00"
    return f"{alpn[0]}{alpn[-1]}"


# ── Legacy hash (pre-FoxIO, backward compat) ──────────────────────────────────

def _build_ja4_legacy(version: int, ciphers: list[int], ext_types: list[int]) -> str:
    vc     = _VERSION_CODES.get(version, "00")
    prefix = f"t{vc}{len(ciphers):02d}{len(ext_types):02d}"
    ch     = _cipher_hash(ciphers, sort=True)
    # legacy: all exts (incl SNI+ALPN), no sig-algs
    all_exts = sorted(f"{e:04x}" for e in ext_types)
    eh = _sha12(",".join(all_exts)) if all_exts else _JA4_ZERO
    return f"{prefix}_{ch}_{eh}"


# ── Canonical JA4 builder ─────────────────────────────────────────────────────

def _build_ja4(
    *,
    transport: str,
    version: int,
    ciphers: list[int],
    ext_types: list[int],
    sig_algs: list[int],
    sni: str,
    alpn: str,
    sort: bool,
) -> str:
    vc     = _VERSION_CODES.get(version, "00")
    prefix = (
        f"{transport}{vc}"
        f"{'d' if sni else 'i'}"
        f"{min(len(ciphers), 99):02d}"
        f"{min(len(ext_types), 99):02d}"
        f"{_alpn_token(alpn)}"
    )
    ch = _cipher_hash(ciphers, sort=sort)
    eh = _ext_hash(ext_types, sig_algs, sort=sort)
    return f"{prefix}_{ch}_{eh}"


def _make_result(
    *,
    source: str,
    version: int,
    ciphers: list[int],
    ext_types: list[int],
    sig_algs: list[int],
    sni: str,
    alpn: str,
    transport: str = "t",
) -> dict:
    canonical = _build_ja4(
        transport=transport, version=version, ciphers=ciphers,
        ext_types=ext_types, sig_algs=sig_algs, sni=sni, alpn=alpn, sort=True,
    )
    raw = _build_ja4(
        transport=transport, version=version, ciphers=ciphers,
        ext_types=ext_types, sig_algs=sig_algs, sni=sni, alpn=alpn, sort=False,
    )
    legacy = _build_ja4_legacy(version, ciphers, ext_types)
    return {
        "ja4":          canonical,
        "ja4_raw":      raw,
        "ja4_legacy":   legacy,
        "ja4_source":   source,
        "ja4_version":  _JA4_VERSION,
        "sni":          sni,
        "alpn":         alpn,
        "tls_version":  _VERSION_STRINGS.get(version, f"0x{version:04x}"),
        "cipher_count": len(ciphers),
        "ext_count":    len(ext_types),
    }


# ── Sig-alg extraction helpers ────────────────────────────────────────────────

def _coerce_int(value) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        if len(value) == 1: return value[0]
        if len(value) == 2: return (value[0] << 8) | value[1]
        return None
    try:
        return int(value)
    except Exception:
        return None


def _sig_algs_from_scapy(ext) -> list[int]:
    raw = None
    for attr in ("sig_algs", "algs", "signature_algs", "signature_algorithms"):
        raw = getattr(ext, attr, None)
        if raw:
            break
    if not raw:
        return []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    result: list[int] = []
    for item in raw:
        if hasattr(item, "sig_alg"):
            item = getattr(item, "sig_alg")
        elif hasattr(item, "hash_alg") and hasattr(item, "sig_alg"):
            h = _coerce_int(getattr(item, "hash_alg"))
            s = _coerce_int(getattr(item, "sig_alg"))
            if h is not None and s is not None:
                item = (h << 8) | s
        v = _coerce_int(item)
        if v is not None and v not in _GREASE:
            result.append(v)
    return result


def _sig_algs_from_raw(data: bytes) -> list[int]:
    if len(data) < 2:
        return []
    list_len = (data[0] << 8) | data[1]
    end = min(2 + list_len, len(data))
    result: list[int] = []
    pos = 2
    while pos + 2 <= end:
        v = (data[pos] << 8) | data[pos + 1]
        if v not in _GREASE:
            result.append(v)
        pos += 2
    return result


# ── Raw TCP parser ────────────────────────────────────────────────────────────

def parse_tls_client_hello_raw(data: bytes) -> dict | None:
    """Parse TLS ClientHello from raw TCP payload bytes.

    Never raises — all buffer accesses are bounds-checked.
    Returns None for non-ClientHello, truncated, or malformed data.
    Limitation: no TCP reassembly (ClientHello split across segments → None).
    """
    if len(data) < 44:
        _stats.failed += 1; _stats.truncated += 1; return None
    if data[0] != 0x16 or data[1] != 0x03:
        _stats.failed += 1; _stats.not_client_hello += 1; return None

    record_len = (data[3] << 8) | data[4]
    if len(data) < 5 + record_len:
        _stats.failed += 1; _stats.truncated += 1; return None
    if data[5] != 0x01:
        _stats.failed += 1; _stats.not_client_hello += 1; return None

    hs_len = (data[6] << 16) | (data[7] << 8) | data[8]
    hs_end = 9 + hs_len
    if len(data) < hs_end:
        _stats.failed += 1; _stats.truncated += 1; return None

    pos = 9
    # client_version
    if pos + 2 > hs_end: _stats.failed += 1; _stats.malformed += 1; return None
    client_version = (data[pos] << 8) | data[pos + 1]; pos += 2
    # random (32 bytes)
    pos += 32
    if pos > hs_end: _stats.failed += 1; _stats.malformed += 1; return None
    # session_id
    if pos + 1 > hs_end: _stats.failed += 1; _stats.malformed += 1; return None
    pos += 1 + data[pos]
    if pos > hs_end: _stats.failed += 1; _stats.malformed += 1; return None
    # cipher_suites
    if pos + 2 > hs_end: _stats.failed += 1; _stats.malformed += 1; return None
    cs_len = (data[pos] << 8) | data[pos + 1]; pos += 2
    if pos + cs_len > hs_end: _stats.failed += 1; _stats.malformed += 1; return None
    ciphers: list[int] = []
    cs_end = pos + cs_len
    while pos + 2 <= cs_end:
        c = (data[pos] << 8) | data[pos + 1]
        if c not in _GREASE: ciphers.append(c)
        pos += 2
    pos = cs_end
    # compression_methods
    if pos + 1 > hs_end: _stats.failed += 1; _stats.malformed += 1; return None
    pos += 1 + data[pos]
    if pos > hs_end: _stats.failed += 1; _stats.malformed += 1; return None

    ext_types: list[int] = []
    sig_algs:  list[int] = []
    sni       = ""
    alpn      = ""
    detected  = client_version

    if pos + 2 <= hs_end:
        exts_len  = (data[pos] << 8) | data[pos + 1]; pos += 2
        exts_end  = min(pos + exts_len, hs_end)
        while pos + 4 <= exts_end:
            et    = (data[pos] << 8) | data[pos + 1]
            edlen = (data[pos + 2] << 8) | data[pos + 3]; pos += 4
            eend  = pos + edlen
            if eend > exts_end: break
            edata = data[pos:eend]

            if et not in _GREASE:
                ext_types.append(et)
                if et == _EXT_SNI and edlen >= 5 and data[pos + 2] == 0x00:
                    nl = (data[pos + 3] << 8) | data[pos + 4]
                    ne = pos + 5 + nl
                    if ne <= eend:
                        try: sni = data[pos + 5:ne].decode("ascii", errors="replace")
                        except Exception: pass
                elif et == _EXT_ALPN and edlen >= 3:
                    pl = data[pos + 2]; pe = pos + 3 + pl
                    if pe <= eend:
                        try: alpn = data[pos + 3:pe].decode("ascii", errors="replace")
                        except Exception: pass
                elif et == _EXT_SUPPORTED_VERSIONS and edlen >= 3 and pos + 1 <= eend:
                    sv_pos = pos + 1
                    sv_end = sv_pos + data[pos]
                    if sv_end <= eend:
                        while sv_pos + 2 <= sv_end:
                            v = (data[sv_pos] << 8) | data[sv_pos + 1]
                            if v not in _GREASE: detected = max(detected, v)
                            sv_pos += 2
                elif et == _EXT_SIGNATURE_ALGS:
                    sig_algs.extend(_sig_algs_from_raw(edata))
            pos = eend

    _stats.raw_ok += 1
    return _make_result(source="raw_tcp", version=detected, ciphers=ciphers,
                        ext_types=ext_types, sig_algs=sig_algs, sni=sni, alpn=alpn)


# ── Scapy-based parser ────────────────────────────────────────────────────────

def compute_tls_fingerprint_from_scapy(packet) -> dict | None:
    """Extract TLS ClientHello fingerprint from a Scapy packet.

    Path 1: native Scapy TLSClientHello layer (best quality, needs SSLSession).
    Path 2: raw TCP payload fallback (works without session= in AsyncSniffer).

    Never raises. Returns None for non-ClientHello or on any error.
    """
    try:
        from scapy.layers.tls.handshake import TLSClientHello  # type: ignore[import]
    except ImportError:
        _stats.failed += 1; _stats.import_error += 1
        TLSClientHello = None  # type: ignore[assignment,misc]

    # ── Path 1: Scapy dissector ───────────────────────────────────────────────
    try:
        if TLSClientHello is not None and packet.haslayer(TLSClientHello):
            hello = packet[TLSClientHello]
            detected  = getattr(hello, "version", 0x0303) or 0x0303
            ciphers   = [c for c in (getattr(hello, "ciphers", None) or []) if c not in _GREASE]
            exts_raw  = getattr(hello, "ext", None) or []

            ext_types: list[int] = []
            sig_algs:  list[int] = []
            sni = ""; alpn = ""

            for ext in exts_raw:
                et = getattr(ext, "type", -1)
                if et in _GREASE: continue
                ext_types.append(et)

                if et == _EXT_SNI:
                    try:
                        sn_list = getattr(ext, "servernames", [])
                        if sn_list:
                            nb = getattr(sn_list[0], "servername", b"")
                            sni = nb.decode("ascii", errors="replace") if isinstance(nb, bytes) else str(nb)
                    except Exception: pass

                elif et == _EXT_ALPN:
                    try:
                        protos = getattr(ext, "protocols", [])
                        if protos:
                            pb = getattr(protos[0], "protocol", b"")
                            alpn = pb.decode("ascii", errors="replace") if isinstance(pb, bytes) else str(pb)
                    except Exception: pass

                elif et == _EXT_SUPPORTED_VERSIONS:
                    try:
                        versions = getattr(ext, "versions", None) or getattr(ext, "supported_versions", None) or []
                        for v in versions:
                            if hasattr(v, "version"): v = getattr(v, "version")
                            cv = _coerce_int(v)
                            if cv is not None and cv not in _GREASE:
                                detected = max(detected, cv)
                    except Exception: pass

                elif et == _EXT_SIGNATURE_ALGS:
                    sig_algs.extend(_sig_algs_from_scapy(ext))

            _stats.scapy_ok += 1
            return _make_result(source="scapy_tls", version=detected, ciphers=ciphers,
                                ext_types=ext_types, sig_algs=sig_algs, sni=sni, alpn=alpn)
    except Exception as exc:
        _log.debug("[TLS] scapy dissect error: %s", exc)

    # ── Path 2: raw fallback ──────────────────────────────────────────────────
    try:
        if not packet.haslayer("TCP") or not packet.haslayer("Raw"):
            _stats.failed += 1; _stats.not_client_hello += 1; return None
        return parse_tls_client_hello_raw(bytes(packet["Raw"].load))
    except Exception as exc:
        _log.debug("[TLS] raw fallback error: %s", exc)
        _stats.failed += 1; _stats.malformed += 1; return None
