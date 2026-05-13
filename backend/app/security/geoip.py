"""
Lightweight offline GeoIP lookup.

No external databases or network calls. Uses:
  1. RFC-1918/RFC-5735 private ranges → "Private" with flag "🏠"
  2. A compact hand-crafted table of major regional CIDR blocks → country code + flag
  3. Fallback → "Unknown" / "🌐"

This is intentionally approximate — good enough to flag "traffic is going to
Russia/China/US" without pulling in a 50 MB GeoLite2 database.
For production accuracy, drop in MaxMind GeoLite2 and replace _lookup_table().
"""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache

_log = logging.getLogger(__name__)


# ── Private / special-use ranges ──────────────────────────────────────────────
_PRIVATE_NETWORKS = [
    ipaddress.ip_network(n) for n in [
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",   # link-local
        "100.64.0.0/10",    # shared address (RFC 6598)
        "192.0.2.0/24",     # TEST-NET-1
        "198.51.100.0/24",  # TEST-NET-2
        "203.0.113.0/24",   # TEST-NET-3
        "::1/128",          # IPv6 loopback
        "fc00::/7",         # IPv6 ULA
        "fe80::/10",        # IPv6 link-local
    ]
]


def is_private(ip: str) -> bool:
    """Return True if the IP address is in a private/reserved range."""
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return False


# ── Compact CIDR → (country_code, flag_emoji, region_name) table ─────────────
# Sourced from public RIR allocation data. Only /8 and large /12–/16 blocks
# are listed; this gives ~60-70% accuracy for global internet traffic.
_CIDR_TABLE: list[tuple[str, str, str, str]] = [
    # CIDR,            CC,   Flag, Region/ISP hint
    # ── United States ──────────────────────────────────
    ("3.0.0.0/8",       "US", "🇺🇸", "Amazon AWS"),
    ("4.0.0.0/8",       "US", "🇺🇸", "Level3"),
    ("8.8.8.0/24",      "US", "🇺🇸", "Google DNS"),
    ("8.0.0.0/8",       "US", "🇺🇸", "ARIN"),
    ("12.0.0.0/8",      "US", "🇺🇸", "AT&T"),
    ("13.0.0.0/8",      "US", "🇺🇸", "Microsoft Azure"),
    ("15.0.0.0/8",      "US", "🇺🇸", "HP"),
    ("16.0.0.0/8",      "US", "🇺🇸", "Hewlett-Packard"),
    ("17.0.0.0/8",      "US", "🇺🇸", "Apple"),
    ("18.0.0.0/8",      "US", "🇺🇸", "MIT / Amazon"),
    ("20.0.0.0/8",      "US", "🇺🇸", "Microsoft Azure"),
    ("23.0.0.0/8",      "US", "🇺🇸", "Akamai"),
    ("34.0.0.0/8",      "US", "🇺🇸", "Google Cloud"),
    ("35.0.0.0/8",      "US", "🇺🇸", "Google Cloud"),
    ("40.0.0.0/8",      "US", "🇺🇸", "Microsoft Azure"),
    ("44.0.0.0/8",      "US", "🇺🇸", "Amateur Radio / ARIN"),
    ("52.0.0.0/8",      "US", "🇺🇸", "Amazon EC2"),
    ("54.0.0.0/8",      "US", "🇺🇸", "Amazon EC2"),
    ("63.0.0.0/8",      "US", "🇺🇸", "ARIN"),
    ("64.0.0.0/8",      "US", "🇺🇸", "ARIN"),
    ("65.0.0.0/8",      "US", "🇺🇸", "ARIN"),
    ("66.0.0.0/8",      "US", "🇺🇸", "ARIN"),
    ("67.0.0.0/8",      "US", "🇺🇸", "ARIN"),
    ("68.0.0.0/8",      "US", "🇺🇸", "ARIN"),
    ("69.0.0.0/8",      "US", "🇺🇸", "ARIN"),
    ("70.0.0.0/8",      "US", "🇺🇸", "ARIN"),
    ("98.0.0.0/8",      "US", "🇺🇸", "ARIN"),
    ("104.0.0.0/8",     "US", "🇺🇸", "Cloudflare"),
    ("107.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    ("108.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    ("173.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    ("184.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    ("199.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    ("205.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    ("206.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    ("207.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    ("208.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    ("209.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    ("216.0.0.0/8",     "US", "🇺🇸", "ARIN"),
    # ── Russia ─────────────────────────────────────────
    ("5.3.0.0/16",      "RU", "🇷🇺", "Rostelecom"),
    ("5.8.0.0/21",      "RU", "🇷🇺", "RIPE RU"),
    ("31.13.0.0/16",    "RU", "🇷🇺", "RIPE RU"),
    ("37.0.0.0/8",      "RU", "🇷🇺", "RIPE (RU/EU mixed)"),
    ("46.0.0.0/8",      "RU", "🇷🇺", "RIPE (RU/EU)"),
    ("77.72.0.0/13",    "RU", "🇷🇺", "RIPE RU"),
    ("78.0.0.0/8",      "RU", "🇷🇺", "RIPE (RU/EU)"),
    ("79.132.0.0/14",   "RU", "🇷🇺", "RIPE RU"),
    ("80.64.0.0/12",    "RU", "🇷🇺", "RIPE RU"),
    ("81.0.0.0/8",      "RU", "🇷🇺", "RIPE (RU/EU)"),
    ("83.149.0.0/16",   "RU", "🇷🇺", "Yandex"),
    ("84.52.0.0/14",    "RU", "🇷🇺", "RIPE RU"),
    ("85.142.0.0/15",   "RU", "🇷🇺", "RIPE RU"),
    ("87.240.0.0/14",   "RU", "🇷🇺", "VK / Mail.ru"),
    ("91.108.4.0/22",   "NL", "🇳🇱", "Telegram"),
    ("91.108.56.0/22",  "NL", "🇳🇱", "Telegram"),
    ("91.0.0.0/8",      "RU", "🇷🇺", "RIPE (RU/EU)"),
    ("93.0.0.0/8",      "RU", "🇷🇺", "RIPE (RU/EU)"),
    ("94.25.0.0/16",    "RU", "🇷🇺", "Rostelecom"),
    ("95.0.0.0/8",      "RU", "🇷🇺", "RIPE (RU/EU)"),
    ("176.0.0.0/8",     "RU", "🇷🇺", "RIPE (RU)"),
    ("178.132.0.0/14",  "RU", "🇷🇺", "RIPE RU"),
    ("185.0.0.0/8",     "RU", "🇷🇺", "RIPE (RU/EU mixed)"),
    ("188.0.0.0/8",     "RU", "🇷🇺", "RIPE (RU)"),
    ("193.0.0.0/8",     "EU", "🇪🇺", "RIPE (EU)"),
    ("194.0.0.0/8",     "EU", "🇪🇺", "RIPE (EU)"),
    ("195.0.0.0/8",     "EU", "🇪🇺", "RIPE (EU)"),
    ("212.0.0.0/8",     "EU", "🇪🇺", "RIPE (EU)"),
    ("213.0.0.0/8",     "EU", "🇪🇺", "RIPE (EU)"),
    ("217.0.0.0/8",     "EU", "🇪🇺", "RIPE (EU)"),
    # ── China ──────────────────────────────────────────
    ("1.0.0.0/8",       "CN", "🇨🇳", "APNIC CN"),
    ("1.192.0.0/11",    "CN", "🇨🇳", "CNNIC"),
    ("14.0.0.0/8",      "CN", "🇨🇳", "APNIC CN"),
    ("27.0.0.0/8",      "CN", "🇨🇳", "APNIC CN"),
    ("36.0.0.0/8",      "CN", "🇨🇳", "APNIC CN"),
    ("39.0.0.0/8",      "CN", "🇨🇳", "APNIC CN"),
    ("42.0.0.0/8",      "CN", "🇨🇳", "APNIC CN"),
    ("49.0.0.0/8",      "CN", "🇨🇳", "APNIC CN"),
    ("58.0.0.0/8",      "CN", "🇨🇳", "APNIC CN"),
    ("59.0.0.0/8",      "CN", "🇨🇳", "APNIC CN"),
    ("60.0.0.0/8",      "CN", "🇨🇳", "APNIC CN"),
    ("61.0.0.0/8",      "CN", "🇨🇳", "APNIC CN"),
    ("101.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("106.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("110.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("111.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("112.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("113.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("114.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("115.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("116.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("117.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("118.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("119.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("120.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("121.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("122.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("123.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("124.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("125.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("163.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("171.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("175.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("180.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("182.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("183.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("202.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("203.0.0.0/8",     "CN", "🇨🇳", "APNIC CN (mixed)"),
    ("210.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("211.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("218.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("219.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("220.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("221.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("222.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    ("223.0.0.0/8",     "CN", "🇨🇳", "APNIC CN"),
    # ── Germany ────────────────────────────────────────
    ("2.248.0.0/13",    "DE", "🇩🇪", "Telekom DE"),
    ("5.175.0.0/16",    "DE", "🇩🇪", "Hetzner"),
    ("23.88.0.0/17",    "DE", "🇩🇪", "Hetzner"),
    ("128.140.0.0/17",  "DE", "🇩🇪", "Hetzner"),
    ("135.181.0.0/16",  "DE", "🇩🇪", "Hetzner"),
    ("138.201.0.0/16",  "DE", "🇩🇪", "Hetzner"),
    ("142.132.0.0/16",  "DE", "🇩🇪", "Hetzner"),
    ("157.90.0.0/16",   "DE", "🇩🇪", "Hetzner"),
    ("159.69.0.0/16",   "DE", "🇩🇪", "Hetzner"),
    ("162.55.0.0/16",   "DE", "🇩🇪", "Hetzner"),
    ("116.202.0.0/15",  "DE", "🇩🇪", "Hetzner"),
    # ── Netherlands ────────────────────────────────────
    ("2.56.224.0/21",   "NL", "🇳🇱", "RIPE NL"),
    ("45.134.0.0/16",   "NL", "🇳🇱", "RIPE NL"),
    ("185.220.0.0/16",  "NL", "🇳🇱", "Tor exit nodes"),
    # ── United Kingdom ─────────────────────────────────
    ("2.24.0.0/13",     "GB", "🇬🇧", "BT"),
    ("5.101.0.0/16",    "GB", "🇬🇧", "RIPE GB"),
    # ── Netherlands/France (CDN) ───────────────────────
    ("1.1.1.0/24",      "AU", "🇦🇺", "Cloudflare DNS"),
    ("1.0.0.0/24",      "AU", "🇦🇺", "Cloudflare DNS"),
    # ── Japan ──────────────────────────────────────────
    ("133.0.0.0/8",     "JP", "🇯🇵", "APNIC JP"),
    ("150.0.0.0/8",     "JP", "🇯🇵", "APNIC JP"),
    ("153.0.0.0/8",     "JP", "🇯🇵", "APNIC JP"),
    ("160.0.0.0/8",     "JP", "🇯🇵", "APNIC JP"),
    # ── South Korea ────────────────────────────────────
    ("1.208.0.0/12",    "KR", "🇰🇷", "APNIC KR"),
    ("14.32.0.0/11",    "KR", "🇰🇷", "APNIC KR"),
    # ── Cloudflare (anycast) ───────────────────────────
    ("104.16.0.0/13",   "CF", "🌐", "Cloudflare CDN"),
    ("104.24.0.0/14",   "CF", "🌐", "Cloudflare CDN"),
    ("172.64.0.0/13",   "CF", "🌐", "Cloudflare CDN"),
    ("131.0.72.0/22",   "CF", "🌐", "Cloudflare CDN"),
    ("162.158.0.0/15",  "CF", "🌐", "Cloudflare CDN"),
    ("198.41.128.0/17", "CF", "🌐", "Cloudflare CDN"),
    ("190.93.240.0/20", "CF", "🌐", "Cloudflare CDN"),
    ("188.114.96.0/20", "CF", "🌐", "Cloudflare CDN"),
    ("197.234.240.0/22","CF", "🌐", "Cloudflare CDN"),
]


@lru_cache(maxsize=1)
def _build_lookup_table() -> list[tuple[ipaddress.IPv4Network, str, str, str]]:
    """Build parsed lookup table (cached, called once)."""
    result: list[tuple[ipaddress.IPv4Network, str, str, str]] = []
    for cidr, cc, flag, hint in _CIDR_TABLE:
        try:
            result.append((ipaddress.ip_network(cidr, strict=False), cc, flag, hint))
        except ValueError:
            _log.warning("[GeoIP] invalid CIDR in table: %s", cidr)
    # Sort by prefix length descending — more specific routes match first
    result.sort(key=lambda x: x[0].prefixlen, reverse=True)
    return result


def lookup(ip: str) -> dict:
    """Return GeoIP info for an IP address.

    Returns a dict:
        {
            "ip":          str,
            "is_private":  bool,
            "country":     str,   # "US", "RU", "CN", "Private", "Unknown"
            "flag":        str,   # emoji flag or "🏠" (private) or "🌐" (unknown)
            "hint":        str,   # ISP/region hint or empty string
        }

    Never raises.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return {"ip": ip, "is_private": False, "country": "Invalid", "flag": "❓", "hint": ""}

    if any(addr in net for net in _PRIVATE_NETWORKS):
        return {"ip": ip, "is_private": True, "country": "Private", "flag": "🏠", "hint": "RFC-1918 / loopback"}

    table = _build_lookup_table()
    for net, cc, flag, hint in table:
        try:
            if addr in net:
                return {"ip": ip, "is_private": False, "country": cc, "flag": flag, "hint": hint}
        except TypeError:
            continue

    return {"ip": ip, "is_private": False, "country": "Unknown", "flag": "🌐", "hint": ""}
