"""Unit tests for MITRE ATT&CK mapping."""
import pytest
from app.mitre.mapping import get_mitre, MITRE_MAP


def test_ddos_mapping() -> None:
    m = get_mitre("DDoS")
    assert m is not None
    assert m["id"] == "T1498"
    assert m["tactic"] == "Impact"
    assert "name" in m


def test_dga_domain_mapping() -> None:
    m = get_mitre("DGA_DOMAIN")
    assert m is not None
    assert "T1568" in m["id"]
    assert m["tactic"] == "Command & Control"


def test_dns_tunneling_mapping() -> None:
    m = get_mitre("DNS_TUNNELING")
    assert m is not None
    assert "T1071" in m["id"]
    assert m["tactic"] == "Command & Control"


def test_unknown_class_returns_none() -> None:
    assert get_mitre("UnknownAttack") is None


def test_none_input_returns_none() -> None:
    assert get_mitre(None) is None


def test_all_entries_have_required_fields() -> None:
    for key, val in MITRE_MAP.items():
        assert "id" in val,     f"{key}: missing 'id'"
        assert "name" in val,   f"{key}: missing 'name'"
        assert "tactic" in val, f"{key}: missing 'tactic'"


@pytest.mark.parametrize("attack_class", ["DoS", "Recon", "BruteForce", "WebAttack", "Bot"])
def test_common_classes_mapped(attack_class: str) -> None:
    assert get_mitre(attack_class) is not None
