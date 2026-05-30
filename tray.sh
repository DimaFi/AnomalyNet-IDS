#!/usr/bin/env bash
# AnomalyNet Control — tray app launcher (Linux)
# Starts the system-tray controller using the venv python.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend"

if [ -x "$SCRIPT_DIR/backend/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/backend/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

# Run detached so the tray survives the launching shell/login script
nohup "$PYTHON" -m app.tray.main >"$SCRIPT_DIR/anomalynet-tray.log" 2>&1 &
echo "AnomalyNet Control (tray) started, PID $!"
