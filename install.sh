#!/usr/bin/env bash
# ============================================================
#  AnomalyNet — Linux install script
#  Tested on: Ubuntu 22.04 / 24.04, Debian 12
#
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/DimaFi/AnomalyNet-gui/main/install.sh | bash
#  or:
#    chmod +x install.sh && ./install.sh
#
#  Options (env vars before running):
#    INTERFACE=eth0          network interface for live capture
#    MODEL_DIR=/opt/model    path to already-downloaded AnomalyNet-ml
#    INSTALL_DIR=/opt/anomalynet
#    AUTO_BLOCK=false
# ============================================================
set -euo pipefail

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${CYAN}►  $*${NC}"; }
ok()   { echo -e "${GREEN}✓  $*${NC}"; }
warn() { echo -e "${YELLOW}⚠  $*${NC}"; }
err()  { echo -e "${RED}✗  $*${NC}"; exit 1; }

# ── Config ───────────────────────────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-/opt/anomalynet}"
GUI_REPO="https://github.com/DimaFi/AnomalyNet-gui.git"
ML_REPO="https://github.com/DimaFi/AnomalyNet-ml.git"
MODEL_DIR="${MODEL_DIR:-$INSTALL_DIR/AnomalyNet-ml}"
AUTO_BLOCK="${AUTO_BLOCK:-false}"

# Detect default interface (first non-loopback)
detect_interface() {
    ip -o link show | awk -F': ' '$2 !~ /lo|docker|br-|virbr/ {print $2; exit}'
}
INTERFACE="${INTERFACE:-$(detect_interface)}"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║       AnomalyNet Installer           ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
log "Install dir : $INSTALL_DIR"
log "Interface   : $INTERFACE"
log "Model dir   : $MODEL_DIR"
echo ""

# ── 1. System dependencies ───────────────────────────────────
log "Installing system packages..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        python3 python3-pip python3-venv python3-dev \
        libpcap-dev libpcap0.8 \
        nodejs npm \
        git curl wget \
        net-tools iproute2 2>/dev/null || true
    # Node 18+ (Ubuntu 22 ships 12 by default)
    NODE_VER=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1 || echo "0")
    if [ "$NODE_VER" -lt 18 ]; then
        warn "Node.js $NODE_VER is too old, installing v20 via NodeSource..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
    fi
elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3 python3-pip libpcap libpcap-devel nodejs npm git
else
    err "Unsupported package manager. Install manually: python3, nodejs, libpcap-dev, git"
fi
ok "System packages ready"

# ── 2. Clone / update repos ───────────────────────────────────
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

if [ -d "AnomalyNet-gui/.git" ]; then
    log "Updating AnomalyNet-gui..."
    git -C AnomalyNet-gui pull --quiet
else
    log "Cloning AnomalyNet-gui..."
    git clone --quiet "$GUI_REPO" AnomalyNet-gui
fi

if [ -d "$MODEL_DIR/.git" ]; then
    log "Updating AnomalyNet-ml..."
    git -C "$MODEL_DIR" pull --quiet
else
    log "Cloning AnomalyNet-ml (model + artifacts, ~15 MB)..."
    git clone --quiet "$ML_REPO" "$MODEL_DIR"
fi
ok "Repos ready"

# ── 3. Python venv + deps ─────────────────────────────────────
GUI_DIR="$INSTALL_DIR/AnomalyNet-gui"
VENV="$GUI_DIR/backend/.venv"

log "Setting up Python venv..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$GUI_DIR/backend/requirements.txt"
ok "Python dependencies installed"

# ── 4. Build frontend ─────────────────────────────────────────
log "Building React frontend..."
cd "$GUI_DIR/frontend"
npm install --silent
npm run build
ok "Frontend built → frontend/dist"

# ── 5. Write settings.json ────────────────────────────────────
log "Writing config/settings.json..."
SETTINGS="$GUI_DIR/config/settings.json"
cat > "$SETTINGS" <<SETTINGS_EOF
{
  "run_mode": "linux_live",
  "model_id": "catboost-iot-v1",
  "interface_name": "${INTERFACE}",
  "catboost_model_dir": "${MODEL_DIR}/model",
  "preprocessing_artifacts_dir": "${MODEL_DIR}/artifacts",
  "catboost_threshold": 0.70,
  "auto_block": ${AUTO_BLOCK},
  "mock_interval_ms": 800,
  "max_events": 500
}
SETTINGS_EOF
ok "Config written (interface: $INTERFACE)"

# ── 6. Startup script ─────────────────────────────────────────
START_SCRIPT="$INSTALL_DIR/start_anomalynet.sh"
cat > "$START_SCRIPT" <<'SCRIPT_EOF'
#!/usr/bin/env bash
# AnomalyNet — start script
# Must run as root (scapy needs raw socket)
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
GUI_DIR="$INSTALL_DIR/AnomalyNet-gui"
VENV="$GUI_DIR/backend/.venv"

if [ "$(id -u)" -ne 0 ]; then
    echo "⚠  Restarting with sudo (scapy requires root)..."
    exec sudo "$0" "$@"
fi

echo "  ╔══════════════════════════════════════╗"
echo "  ║        AnomalyNet  started           ║"
echo "  ║   http://$(hostname -I | awk '{print $1}'):8000    ║"
echo "  ╚══════════════════════════════════════╝"

cd "$GUI_DIR/backend"
exec "$VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level warning
SCRIPT_EOF
chmod +x "$START_SCRIPT"
ok "Start script → $START_SCRIPT"

# ── 7. Systemd service (optional) ────────────────────────────
SERVICE="/etc/systemd/system/anomalynet.service"
log "Creating systemd service..."
sudo tee "$SERVICE" > /dev/null <<SERVICE_EOF
[Unit]
Description=AnomalyNet IDS
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${GUI_DIR}/backend
ExecStart=${VENV}/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning
Restart=on-failure
RestartSec=5
Environment=ANOMALYNET_APP_ROOT=${GUI_DIR}

[Install]
WantedBy=multi-user.target
SERVICE_EOF

sudo systemctl daemon-reload
sudo systemctl enable anomalynet 2>/dev/null || true
ok "Systemd service installed (anomalynet.service)"

# ── Done ──────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation complete!${NC}"
echo ""
echo -e "  Start manually:  ${CYAN}sudo $START_SCRIPT${NC}"
echo -e "  Start as service:${CYAN}sudo systemctl start anomalynet${NC}"
echo -e "  Open in browser: ${CYAN}http://${IP}:8000${NC}"
echo ""
echo -e "  Logs:  journalctl -u anomalynet -f"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
