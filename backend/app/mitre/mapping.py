from __future__ import annotations

_BASE = "https://attack.mitre.org/techniques/"

MITRE_MAP: dict[str, dict[str, str]] = {
    # Flow-based attack classes
    "DoS":          {"id": "T1498",     "name": "Network Denial of Service",              "tactic": "Impact",               "url": f"{_BASE}T1498/"},
    "DDoS":         {"id": "T1498",     "name": "Network Denial of Service",              "tactic": "Impact",               "url": f"{_BASE}T1498/"},
    "Mirai":        {"id": "T1584",     "name": "Compromise Infrastructure",              "tactic": "Resource Development", "url": f"{_BASE}T1584/"},
    "Bot":          {"id": "T1584",     "name": "Compromise Infrastructure",              "tactic": "Resource Development", "url": f"{_BASE}T1584/"},
    "Botnet":       {"id": "T1584",     "name": "Compromise Infrastructure",              "tactic": "Resource Development", "url": f"{_BASE}T1584/"},
    "Recon":        {"id": "T1595",     "name": "Active Scanning",                        "tactic": "Reconnaissance",       "url": f"{_BASE}T1595/"},
    "PortScan":     {"id": "T1046",     "name": "Network Service Discovery",              "tactic": "Discovery",            "url": f"{_BASE}T1046/"},
    "BruteForce":   {"id": "T1110",     "name": "Brute Force",                            "tactic": "Credential Access",    "url": f"{_BASE}T1110/"},
    "Spoofing":     {"id": "T1557",     "name": "Adversary-in-the-Middle",                "tactic": "Collection",           "url": f"{_BASE}T1557/"},
    "WebAttack":    {"id": "T1190",     "name": "Exploit Public-Facing Application",      "tactic": "Initial Access",       "url": f"{_BASE}T1190/"},
    "Infiltration": {"id": "T1071",     "name": "Application Layer Protocol",             "tactic": "Command & Control",    "url": f"{_BASE}T1071/"},
    # DNS anomaly types — heuristic mapping, best-effort
    "DGA_DOMAIN":   {"id": "T1568.004", "name": "Fast Flux DNS",                          "tactic": "Command & Control",    "url": f"{_BASE}T1568/004/"},
    "DNS_TUNNELING":{"id": "T1071.004", "name": "Application Layer Protocol: DNS",        "tactic": "Command & Control",    "url": f"{_BASE}T1071/004/"},
    # TLS behavioral anomalies — heuristic mapping
    "NEW_TLS_FINGERPRINT":       {"id": "T1071.001", "name": "Application Layer Protocol: Web Protocols", "tactic": "Command & Control", "url": f"{_BASE}T1071/001/"},
    "TOO_MANY_TLS_FINGERPRINTS": {"id": "T1046",     "name": "Network Service Discovery",                "tactic": "Discovery",         "url": f"{_BASE}T1046/"},
}


def get_mitre(attack_class: str | None) -> dict[str, str] | None:
    if not attack_class:
        return None
    return MITRE_MAP.get(attack_class)
