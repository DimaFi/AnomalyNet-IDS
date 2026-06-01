"""Print the uvicorn bind host based on the allow_remote_access setting.

Used by launch.bat / launch.sh to decide between 127.0.0.1 (local only) and
0.0.0.0 (reachable from other devices on the network). Standalone — stdlib only,
no app imports — so it can run before the server starts.

  prints "0.0.0.0"   when allow_remote_access is true
  prints "127.0.0.1" otherwise (or if the setting can't be read)
"""

import json
import os
import platform
from pathlib import Path


def _data_dir() -> Path:
    override = os.environ.get("ANOMALYNET_DATA_DIR")
    if override:
        return Path(override)
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "anomalynet"


def main() -> None:
    remote = False
    try:
        p = _data_dir() / "settings.json"
        if p.exists():
            remote = bool(json.loads(p.read_text(encoding="utf-8")).get("allow_remote_access"))
    except Exception:
        remote = False
    print("0.0.0.0" if remote else "127.0.0.1")


if __name__ == "__main__":
    main()
