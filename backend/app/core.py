from __future__ import annotations

import os
from pathlib import Path

# Allow launcher / PyInstaller bundle to override the root path
_env = os.environ.get("ANOMALYNET_APP_ROOT")
APP_ROOT: Path = Path(_env) if _env else Path(__file__).resolve().parents[2]
