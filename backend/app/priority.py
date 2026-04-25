from __future__ import annotations

import ipaddress

_PRIVATE = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]

_HIGH_IMPACT   = {"DoS", "DDoS", "Mirai", "Bot"}
_HIGH_CRED     = {"BruteForce", "Infiltration"}


def is_internal(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE)
    except ValueError:
        return False


def calc_priority(score: float, attack_class: str | None, src_ip: str) -> str:
    internal = is_internal(src_ip)

    if score >= 0.95 and internal:
        return "critical"
    if attack_class in _HIGH_IMPACT and score >= 0.90:
        return "critical"

    if score >= 0.85:
        return "high"
    if attack_class in _HIGH_CRED and score >= 0.70:
        return "high"

    if score >= 0.70:
        return "medium"

    return "info"
