"""
AnomalyNet Control — lightweight system-tray app (pystray).

Runs in parallel with the panel and controls it over HTTP:
  • Open panel in browser
  • Start / Restart / Stop panel
  • Live metrics (CPU / RAM / events) in the tooltip and menu header
  • Two independent autostart toggles (panel, tray app)

Entry point:  python -m app.tray.main   (run with cwd = backend/)
"""

from __future__ import annotations

import logging
import sys
import threading
import time


def _setup_logging() -> None:
    """Log to a file in the app root — robust under pythonw (no console)."""
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    try:
        from app.tray.controller import detect_app_root
        logfile = detect_app_root() / "anomalynet-tray.log"
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setFormatter(fmt)
        root_logger.addHandler(fh)
    except Exception:
        pass
    # Also log to stderr when a console is attached (ignored under pythonw)
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root_logger.addHandler(sh)


_setup_logging()
_log = logging.getLogger("app.tray")

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception as exc:  # pragma: no cover - import guard
    sys.stderr.write(
        "AnomalyNet Control requires 'pystray' and 'Pillow'.\n"
        "Install them into the venv:\n"
        "    pip install pystray Pillow\n"
        f"(import error: {exc})\n"
    )
    sys.exit(1)

from app.tray import autostart
from app.tray.controller import PanelController

POLL_INTERVAL_S = 3.0

# Status colors for the corner dot
_COLOR_RUNNING = (34, 197, 94, 255)    # green
_COLOR_STOPPED = (148, 163, 184, 255)  # gray
_COLOR_WARN    = (249, 115, 22, 255)   # orange
_COLOR_CRIT    = (239, 68, 68, 255)    # red


class _State:
    def __init__(self) -> None:
        self.running = False
        self.metrics: dict | None = None


class TrayApp:
    def __init__(self) -> None:
        self.ctl = PanelController()
        self.state = _State()
        self._base_img = self._load_base_image()
        self._stop = threading.Event()
        self.icon = pystray.Icon(
            "anomalynet",
            icon=self._compose_icon(_COLOR_STOPPED),
            title="AnomalyNet Control",
            menu=self._build_menu(),
        )

    # ── Icon image ──────────────────────────────────────────────────────────
    def _load_base_image(self) -> "Image.Image":
        root = self.ctl.root
        for cand in [root / "frontend" / "public" / "logo.png",
                     root / "frontend" / "dist" / "logo.png",
                     root / "frontend" / "public" / "AnomalyNet.ico",
                     root / "frontend" / "dist" / "AnomalyNet.ico"]:
            if cand.exists():
                try:
                    img = Image.open(cand).convert("RGBA")
                    return img.resize((64, 64))
                except Exception:
                    continue
        # Fallback: a plain blue square so the tray still shows something
        img = Image.new("RGBA", (64, 64), (37, 99, 235, 255))
        return img

    def _compose_icon(self, dot_color: tuple) -> "Image.Image":
        img = self._base_img.copy()
        d = ImageDraw.Draw(img)
        r = 18
        x1, y1 = 64 - r - 2, 64 - r - 2
        d.ellipse([x1, y1, x1 + r, y1 + r], fill=dot_color,
                  outline=(255, 255, 255, 255), width=2)
        return img

    def _status_color(self) -> tuple:
        if not self.state.running:
            return _COLOR_STOPPED
        lvl = (self.state.metrics or {}).get("load_level", "low")
        if lvl == "critical":
            return _COLOR_CRIT
        if lvl == "high":
            return _COLOR_WARN
        return _COLOR_RUNNING

    # ── Menu ────────────────────────────────────────────────────────────────
    def _status_text(self, _item=None) -> str:
        if not self.state.running:
            return "● Панель: выключена"
        m = self.state.metrics or {}
        cpu = round(m.get("cpu_percent", 0))
        ram = round(m.get("ram_percent", 0))
        ev = m.get("events_total", 0)
        warn = m.get("events_warning", 0) + m.get("events_anomaly", 0)
        return f"● Панель: работает · CPU {cpu}% · RAM {ram}% · {ev} соб. ({warn} ⚠)"

    def _build_menu(self) -> "pystray.Menu":
        Item = pystray.MenuItem
        return pystray.Menu(
            Item(self._status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Открыть панель в браузере", self._on_open),
            pystray.Menu.SEPARATOR,
            Item("▶  Запустить панель", self._on_start,
                 enabled=lambda i: not self.state.running),
            Item("⟳  Перезапустить панель", self._on_restart,
                 enabled=lambda i: self.state.running),
            Item("■  Остановить панель", self._on_stop,
                 enabled=lambda i: self.state.running),
            pystray.Menu.SEPARATOR,
            Item("Автозапуск панели", self._on_toggle_panel_autostart,
                 checked=lambda i: autostart.is_enabled("panel")),
            Item("Автозапуск приложения", self._on_toggle_tray_autostart,
                 checked=lambda i: autostart.is_enabled("tray")),
            pystray.Menu.SEPARATOR,
            Item("Выход", self._on_quit),
        )

    # ── Actions (run in pystray's thread; keep them quick / non-blocking) ────
    def _on_open(self, *_):
        self.ctl.open_panel()

    def _on_start(self, *_):
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self):
        self.ctl.start()
        self._refresh(force=True)

    def _on_restart(self, *_):
        threading.Thread(target=self._do_restart, daemon=True).start()

    def _do_restart(self):
        self.ctl.restart()
        time.sleep(2)
        self._refresh(force=True)

    def _on_stop(self, *_):
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _do_stop(self):
        self.ctl.stop()
        time.sleep(1)
        self._refresh(force=True)

    def _on_toggle_panel_autostart(self, *_):
        autostart.toggle("panel", self.ctl.root)
        self.icon.update_menu()

    def _on_toggle_tray_autostart(self, *_):
        autostart.toggle("tray", self.ctl.root)
        self.icon.update_menu()

    def _on_quit(self, *_):
        self._stop.set()
        self.icon.stop()

    # ── Polling ─────────────────────────────────────────────────────────────
    def _refresh(self, force: bool = False):
        running = self.ctl.is_running()
        metrics = self.ctl.metrics() if running else None
        changed = (running != self.state.running) or force
        self.state.running = running
        self.state.metrics = metrics
        try:
            self.icon.icon = self._compose_icon(self._status_color())
            self.icon.title = self._status_text()
            self.icon.update_menu()
        except Exception as exc:
            _log.debug("[tray] refresh ui error: %s", exc)
        return changed

    def _poll_loop(self):
        while not self._stop.is_set():
            try:
                self._refresh()
            except Exception as exc:
                _log.debug("[tray] poll error: %s", exc)
            self._stop.wait(POLL_INTERVAL_S)

    def _setup(self, icon):
        icon.visible = True
        self._refresh(force=True)
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def run(self):
        _log.info("[tray] AnomalyNet Control starting (root=%s)", self.ctl.root)
        self.icon.run(setup=self._setup)


def main():
    TrayApp().run()


if __name__ == "__main__":
    main()
