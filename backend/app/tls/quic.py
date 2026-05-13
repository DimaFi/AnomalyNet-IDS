"""
QUIC / JA4Q — QUIC Initial packet fingerprinting.

Future-work stub. Architecture is ready; implementation requires QUIC
packet capture support (UDP port 443 deep inspection with QUIC header
parsing and CRYPTO frame reassembly for TLS ClientHello extraction).

JA4Q format (FoxIO spec, draft):
    q{version}{sni_yn}{cipher_count}{ext_count}_{ciphers_hash}_{extensions_hash}
    e.g. q1_1_0403_e742b0ab7b5c_9f3a812f6c4e

References:
    https://github.com/FoxIO-LLC/ja4/blob/main/technical_details/JA4Q.md
    RFC 9000: QUIC: A UDP-Based Multiplexed and Secure Transport
    RFC 9001: Using TLS to Secure QUIC
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


def is_quic_initial(data: bytes) -> bool:
    """Heuristic check: returns True if the UDP payload looks like a QUIC Initial packet.

    QUIC Long Header: first byte bit 7 = 1 (Long Header flag), bits 5-4 = 00 (Initial).
    Also checks that byte 1-4 matches QUIC version (0x00000001 for QUIC v1, 0x6b3343cf for v2).

    TODO: Tighten detection — QUIC v2 uses different packet type encoding.
    """
    if len(data) < 5:
        return False
    first_byte = data[0]
    if not (first_byte & 0x80):
        return False  # Short header — not Initial
    if not ((first_byte & 0x30) == 0x00):
        return False  # Not Initial packet type
    version = int.from_bytes(data[1:5], "big")
    return version in (0x00000001, 0x6b3343cf)


def extract_quic_client_hello(data: bytes) -> bytes | None:
    """Extract the TLS ClientHello bytes from a QUIC Initial packet's CRYPTO frame.

    Returns the raw ClientHello bytes or None if extraction fails.
    Never raises.

    TODO: Implement full QUIC Initial packet parser:
          1. Parse Long Header: version, DCID length, DCID, SCID length, SCID
          2. Derive QUIC Initial secrets from DCID (HKDF-SHA256 with known salt)
          3. Decrypt QUIC Initial packet payload (AES-128-GCM or ChaCha20-Poly1305)
          4. Parse decrypted QUIC frames looking for CRYPTO frame (type 0x06)
          5. Extract CRYPTO frame data — this is the TLS record
          6. Skip TLS record header (5 bytes) to get raw ClientHello bytes
          7. Handle fragmented CRYPTO frames (reassembly by offset field)

    Note: QUIC Initial packets use a fixed HKDF salt defined in RFC 9001 §5.2.
    The ClientHello is always in the CRYPTO frame of the Initial packet, unencrypted
    at the connection level (only QUIC packet protection, not application-level TLS).
    """
    # TODO: implement QUIC Initial decryption and CRYPTO frame extraction
    _log.debug("[QUIC] extract_client_hello stub called — not implemented yet")
    return None


def compute_ja4q_from_scapy(packet) -> dict | None:
    """Compute JA4Q fingerprint from a Scapy UDP packet carrying QUIC Initial data.

    Returns None if the packet is not a QUIC Initial or processing fails.
    Never raises.

    TODO: Implement once extract_quic_client_hello() is complete:
          1. Verify packet has UDP layer and src/dst port == 443 (or any high port)
          2. Extract UDP payload
          3. Call is_quic_initial() to filter
          4. Call extract_quic_client_hello() to get TLS ClientHello bytes
          5. Parse ClientHello using the raw parser logic from fingerprint.py
          6. Apply JA4Q formula (same as JA4 but with q prefix and QUIC version)
          7. Return {"ja4q": ja4q_string, "quic_version": version_str,
                     "sni": sni, "ciphers": cipher_list, "extensions": ext_list}
    """
    # TODO: implement JA4Q
    _log.debug("[QUIC] ja4q stub called — not implemented yet")
    return None
