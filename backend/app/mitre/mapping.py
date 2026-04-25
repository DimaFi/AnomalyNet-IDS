from __future__ import annotations

MITRE_MAP: dict[str, dict[str, str]] = {
    "DoS":          {"id": "T1498", "name": "Network Denial of Service",   "tactic": "Impact"},
    "DDoS":         {"id": "T1498", "name": "Network Denial of Service",   "tactic": "Impact"},
    "Mirai":        {"id": "T1584", "name": "Compromise Infrastructure",   "tactic": "Resource Development"},
    "Bot":          {"id": "T1584", "name": "Compromise Infrastructure",   "tactic": "Resource Development"},
    "Botnet":       {"id": "T1584", "name": "Compromise Infrastructure",   "tactic": "Resource Development"},
    "Recon":        {"id": "T1595", "name": "Active Scanning",             "tactic": "Reconnaissance"},
    "PortScan":     {"id": "T1046", "name": "Network Service Discovery",   "tactic": "Discovery"},
    "BruteForce":   {"id": "T1110", "name": "Brute Force",                 "tactic": "Credential Access"},
    "Spoofing":     {"id": "T1557", "name": "Adversary-in-the-Middle",     "tactic": "Collection"},
    "WebAttack":    {"id": "T1190", "name": "Exploit Public-Facing App",   "tactic": "Initial Access"},
    "Infiltration": {"id": "T1071", "name": "Application Layer Protocol",  "tactic": "Command & Control"},
}


def get_mitre(attack_class: str | None) -> dict[str, str] | None:
    if not attack_class:
        return None
    return MITRE_MAP.get(attack_class)
