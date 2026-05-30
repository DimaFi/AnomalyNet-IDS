#!/usr/bin/env bash
# AnomalyNet IDS — Linux Uninstaller
echo ""
echo " AnomalyNet IDS | Uninstaller"
echo ""

# Stop server + tray app
curl -s -X POST http://localhost:8000/api/update/stop >/dev/null 2>&1 || true
pkill -f "app.tray.main" 2>/dev/null || true

# Remove shortcuts and autostart (panel + tray)
rm -f "$HOME/.local/share/applications/anomalynet.desktop"
rm -f "$HOME/Desktop/anomalynet.desktop"
rm -f "$HOME/.config/autostart/anomalynet.desktop"
rm -f "$HOME/.config/autostart/anomalynet-tray.desktop"
command -v update-desktop-database &>/dev/null && \
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo " Removed shortcuts and autostart entries (panel + tray)."
echo " The application folder was NOT deleted."
echo ""
