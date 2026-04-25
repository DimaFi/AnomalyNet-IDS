import pytest
from pathlib import Path


@pytest.fixture
def tmp_history_dir(tmp_path: Path) -> Path:
    d = tmp_path / "history"
    d.mkdir()
    return d
