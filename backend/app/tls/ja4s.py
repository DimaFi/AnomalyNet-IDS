"""
JA4S — TLS ServerHello fingerprinting.

Future-work stub. Architecture is ready; implementation follows once
server-side TLS capture is enabled (requires full TCP stream reassembly
so both ClientHello and ServerHello are visible to the same capture hook).

JA4S format (FoxIO spec):
    t{version}{cipher}_{extensions_hash}_{alpn_first_protocol}
    e.g. t131301_c02b001700ff_h2

References:
    https://github.com/FoxIO-LLC/ja4/blob/main/technical_details/JA4S.md
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


def compute_ja4s_from_scapy(packet) -> dict | None:
    """Parse TLS ServerHello from a Scapy packet and return a JA4S fingerprint dict.

    Returns None if the packet is not a ServerHello or parsing fails.
    Thread-safe; never raises.

    TODO: Implement when server-side capture is available.
          Requires packet to have both SrcIP=server and TLSServerHello layer.
          Steps:
            1. Extract TLSServerHello from packet
            2. Read chosen_cipher_suite (single value)
            3. Read extensions list, filter GREASE, sort by type
            4. Extract ALPN selected protocol (ext 0x0010) if present
            5. Compute:
               version_code = TLS version string (e.g. "1301" for TLS 1.3)
               cipher_hex   = hex(chosen_cipher_suite)[2:].zfill(4)
               ext_hash     = sha256(",".join(hex(e) for e in sorted_ext_types))[:12]
               alpn_first   = first protocol from ALPN ext, or "00"
               ja4s = f"t{version_code}_{cipher_hex}{ext_hash}_{alpn_first}"
            6. Return {"ja4s": ja4s, "cipher": chosen_cipher_suite_hex,
                       "version": version_str, "alpn": alpn_first}
    """
    # TODO: implement ServerHello parsing
    _log.debug("[JA4S] stub called — not implemented yet")
    return None


def compute_ja4s_raw(data: bytes, src_ip: str, dst_ip: str) -> dict | None:
    """Parse JA4S from raw TLS record bytes (fallback path for non-Scapy capture).

    Returns None if data is not a TLS ServerHello or parsing fails.
    Never raises.

    TODO: Implement using manual TLS record parser similar to fingerprint.py:
          1. Verify TLS record type == 0x16 (Handshake) at offset 0
          2. Verify handshake type == 0x02 (ServerHello) at offset 5
          3. Parse ServerHello fields: version, random, session_id_len, cipher_suite,
             compression_method, extensions length, extension list
          4. Apply same JA4S formula as compute_ja4s_from_scapy
    """
    # TODO: implement raw ServerHello parsing
    _log.debug("[JA4S] raw stub called — not implemented yet")
    return None
