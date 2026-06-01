"""
Public access via Cloudflare Tunnel (cloudflared quick tunnel).

Gives a public https://<random>.trycloudflare.com URL that forwards to the local
panel — no router config, no account. The cloudflared binary is downloaded from
GitHub releases (reachable even where pypi is blocked) into the user data dir.

The URL is ephemeral: it changes every time the tunnel is (re)started.
"""

from __future__ import annotations

import logging
import platform
import re
import subprocess
import threading
import urllib.request
from pathlib import Path

from app.core import get_user_data_dir

_log = logging.getLogger("app.remote.tunnel")

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

_DOWNLOAD = {
    ("Windows", "amd64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    ("Linux",   "amd64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
    ("Linux",   "arm64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64",
    ("Darwin",  "amd64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz",
}


def _arch() -> str:
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    return "amd64"


def _bin_path() -> Path:
    name = "cloudflared.exe" if platform.system() == "Windows" else "cloudflared"
    return get_user_data_dir() / "bin" / name


def ensure_binary() -> Path:
    """Return path to cloudflared, downloading it once if missing."""
    dest = _bin_path()
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    url = _DOWNLOAD.get((platform.system(), _arch()))
    if not url:
        raise RuntimeError(f"cloudflared недоступен для {platform.system()}/{_arch()}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _log.info("[tunnel] downloading cloudflared from %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "AnomalyNet/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest.write_bytes(resp.read())
    if platform.system() != "Windows":
        dest.chmod(0o755)
    return dest


class TunnelManager:
    """Singleton-ish manager for one cloudflared quick tunnel."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._url: str = ""
        self._lock = threading.Lock()

    def status(self) -> dict:
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            if not running:
                self._url = ""
            return {"running": running, "url": self._url}

    def start(self, port: int = 8000, timeout: float = 35.0) -> dict:
        """Start the tunnel and wait for the public URL. Idempotent."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None and self._url:
                return {"running": True, "url": self._url}

        binary = ensure_binary()
        cmd = [str(binary), "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"]
        _log.info("[tunnel] starting: %s", " ".join(cmd))

        creationflags = 0x08000000 if platform.system() == "Windows" else 0  # CREATE_NO_WINDOW
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, creationflags=creationflags,
        )

        url = ""
        import time
        deadline = time.monotonic() + timeout
        assert proc.stdout is not None
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            m = _URL_RE.search(line)
            if m:
                url = m.group(0)
                break

        if not url:
            try:
                proc.terminate()
            except Exception:
                pass
            raise RuntimeError("Не удалось получить публичный URL от cloudflared (таймаут/блокировка сети).")

        # Keep draining stdout so the pipe doesn't fill and block cloudflared.
        threading.Thread(target=self._drain, args=(proc,), daemon=True).start()

        with self._lock:
            self._proc = proc
            self._url = url
        _log.info("[tunnel] public URL: %s", url)
        return {"running": True, "url": url}

    def _drain(self, proc: subprocess.Popen) -> None:
        try:
            assert proc.stdout is not None
            for _ in proc.stdout:
                pass
        except Exception:
            pass

    def stop(self) -> dict:
        with self._lock:
            proc, self._proc, self._url = self._proc, None, ""
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
            except Exception:
                pass
        return {"running": False, "url": ""}


# Module-level singleton
tunnel = TunnelManager()
