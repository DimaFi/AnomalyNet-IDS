#!/usr/bin/env bash
# AnomalyNet IDS — Linux/macOS Launcher
# Run: bash launch.sh  or  chmod +x launch.sh && ./launch.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT=8000

# Find Python: prefer venv, then system
if [ -x "backend/.venv/bin/python" ]; then
    PYTHON="backend/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "Python not found. Please install Python 3.10+ or run: sudo bash install.sh"
    exit 1
fi

# Check if already running
if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/health" 2>/dev/null | grep -q "200"; then
    echo "AnomalyNet already running — opening browser..."
    if command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:$PORT"
    elif command -v open &>/dev/null; then
        open "http://localhost:$PORT"
    fi
    exit 0
fi

echo "Starting AnomalyNet IDS..."
nohup "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --app-dir backend \
    >"${SCRIPT_DIR}/anomalynet.log" 2>&1 &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"

# Wait for server (up to 15 seconds)
for i in $(seq 1 15); do
    sleep 1
    if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/health" 2>/dev/null | grep -q "200"; then
        echo "Ready!"
        if command -v xdg-open &>/dev/null; then
            xdg-open "http://localhost:$PORT"
        elif command -v open &>/dev/null; then
            open "http://localhost:$PORT"
        fi
        exit 0
    fi
done

echo "Server started (PID $SERVER_PID). Opening browser..."
if command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:$PORT"
fi
