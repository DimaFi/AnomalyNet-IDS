"""Unit tests for calc_priority()."""
import pytest
from app.priority import calc_priority


def test_critical_internal_high_score() -> None:
    assert calc_priority(0.96, "DDoS", "192.168.1.10") == "critical"


def test_critical_high_impact_class() -> None:
    assert calc_priority(0.92, "DDoS", "1.2.3.4") == "critical"


def test_high_score() -> None:
    assert calc_priority(0.88, None, "1.2.3.4") == "high"


def test_high_cred_class() -> None:
    assert calc_priority(0.75, "BruteForce", "1.2.3.4") == "high"


def test_medium_score() -> None:
    assert calc_priority(0.72, None, "1.2.3.4") == "medium"


def test_info_low_score() -> None:
    assert calc_priority(0.30, None, "1.2.3.4") == "info"


@pytest.mark.parametrize("src_ip,score,expected", [
    ("192.168.1.1", 0.96, "critical"),   # internal + high score
    ("8.8.8.8",    0.96, "high"),        # external, same score → not critical
])
def test_internal_vs_external(src_ip: str, score: float, expected: str) -> None:
    assert calc_priority(score, None, src_ip) == expected
