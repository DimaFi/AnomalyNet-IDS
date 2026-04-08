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
#    DETECTION_MODE=simple   "simple" (Stage1+Stage2) or "advanced" (Stage1+Stage3)
#    AUTO_BLOCK=false
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${CYAN}>  $*${NC}"; }
ok()   { echo -e "${GREEN}[OK] $*${NC}"; }
warn() { echo -e "${YELLOW}[WARN] $*${NC}"; }
err()  { echo -e "${RED}[ERR] $*${NC}"; exit 1; }

# ── Config ───────────────────────────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-/opt/anomalynet}"
GUI_REPO="https://github.com/DimaFi/AnomalyNet-gui.git"
ML_REPO="https://github.com/DimaFi/AnomalyNet-ml.git"
MODEL_DIR="${MODEL_DIR:-$INSTALL_DIR/AnomalyNet-ml}"
AUTO_BLOCK="${AUTO_BLOCK:-false}"
DETECTION_MODE="${DETECTION_MODE:-simple}"

detect_interface() {
    ip -o link show | awk -F': ' '$2 !~ /lo|docker|br-|virbr/ {print $2; exit}'
}
INTERFACE="${INTERFACE:-$(detect_interface)}"

echo ""
echo "  +--------------------------------------+"
echo "  |       AnomalyNet Installer           |"
echo "  +--------------------------------------+"
echo ""
log "Install dir     : $INSTALL_DIR"
log "Interface       : $INTERFACE"
log "Model dir       : $MODEL_DIR"
log "Detection mode  : $DETECTION_MODE"
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
    log "Cloning AnomalyNet-ml (models + artifacts)..."
    git clone --quiet "$ML_REPO" "$MODEL_DIR"
fi
ok "Repos ready"

# ── Model paths ───────────────────────────────────────────────
STAGE1_MODEL_DIR="$MODEL_DIR/model"
STAGE1_ARTIFACTS="$MODEL_DIR/artifacts"
STAGE2_MODEL_DIR="$MODEL_DIR/stage2_multiclass/models/catboost"
STAGE3_MODEL_DIR="$MODEL_DIR/stage3_cic2023/models/catboost"
STAGE3_ARTIFACTS="$MODEL_DIR/stage3_cic2023/artifacts"

# Select cascade model based on detection mode
if [ "$DETECTION_MODE" = "advanced" ]; then
    ACTIVE_MODEL_ID="catboost-cascade-advanced"
    SEC_MODEL_DIR="$STAGE3_MODEL_DIR"
    SEC_ARTIFACTS="$STAGE3_ARTIFACTS"
else
    ACTIVE_MODEL_ID="catboost-cascade-simple"
    SEC_MODEL_DIR="$STAGE2_MODEL_DIR"
    SEC_ARTIFACTS=""
fi

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
ok "Frontend built"

# ── 5. Write settings.json ────────────────────────────────────
log "Writing config/settings.json..."
SETTINGS="$GUI_DIR/config/settings.json"
cat > "$SETTINGS" <<SETTINGS_EOF
{
  "language": "ru",
  "theme": "dark",
  "run_mode": "linux_live",
  "retention_days": 14,
  "active_model_id": "${ACTIVE_MODEL_ID}",
  "capture_enabled": true,
  "stream_autostart": true,
  "interface_name": "${INTERFACE}",
  "catboost_threshold": 0.70,
  "catboost_model_dir": "${STAGE1_MODEL_DIR}",
  "preprocessing_artifacts_dir": "${STAGE1_ARTIFACTS}",
  "auto_block": ${AUTO_BLOCK},
  "detection_mode": "${DETECTION_MODE}",
  "catboost_secondary_model_dir": "${SEC_MODEL_DIR}",
  "catboost_secondary_artifacts_dir": "${SEC_ARTIFACTS}"
}
SETTINGS_EOF
ok "Config written (mode: $DETECTION_MODE, iface: $INTERFACE)"

# ── 6. Update presets with actual paths ───────────────────────
log "Configuring model presets..."
# The store reads ANOMALYNET_MODELS_ROOT to resolve preset paths
# We bake the actual paths into the presets file for clarity
PRESETS="$GUI_DIR/config/model_presets.json"
cat > "$PRESETS" <<PRESETS_EOF
{
  "presets": [
    {
      "id": "mock",
      "name": "Demo (Mock)",
      "description": "Demo mode - no real traffic capture. Works without root.",
      "icon": "demo",
      "active_model_id": "mock-default",
      "run_mode": "mock",
      "detection_mode": "simple",
      "catboost_model_dir": "",
      "preprocessing_artifacts_dir": "",
      "catboost_secondary_model_dir": "",
      "catboost_secondary_artifacts_dir": ""
    },
    {
      "id": "binary-v1",
      "name": "Binary Detector (Stage1)",
      "description": "Binary: Benign/Attack. Fast, F1=99.4%. No attack type.",
      "icon": "binary",
      "active_model_id": "catboost-iot-v1",
      "run_mode": "linux_live",
      "detection_mode": "simple",
      "catboost_model_dir": "${STAGE1_MODEL_DIR}",
      "preprocessing_artifacts_dir": "${STAGE1_ARTIFACTS}",
      "catboost_secondary_model_dir": "",
      "catboost_secondary_artifacts_dir": ""
    },
    {
      "id": "simple-cascade",
      "name": "Simple Cascade (Stage1 + Stage2)",
      "description": "Binary gate + 8-class detector. 71 CICFlowMeter features. Macro F1=0.31.",
      "icon": "simple",
      "active_model_id": "catboost-cascade-simple",
      "run_mode": "linux_live",
      "detection_mode": "simple",
      "catboost_model_dir": "${STAGE1_MODEL_DIR}",
      "preprocessing_artifacts_dir": "${STAGE1_ARTIFACTS}",
      "catboost_secondary_model_dir": "${STAGE2_MODEL_DIR}",
      "catboost_secondary_artifacts_dir": ""
    },
    {
      "id": "advanced-cascade",
      "name": "Advanced Cascade (Stage1 + Stage3 IoT2023)",
      "description": "Binary gate + IoT2023 classifier. 71+46 features. Macro F1=0.819.",
      "icon": "advanced",
      "active_model_id": "catboost-cascade-advanced",
      "run_mode": "linux_live",
      "detection_mode": "advanced",
      "catboost_model_dir": "${STAGE1_MODEL_DIR}",
      "preprocessing_artifacts_dir": "${STAGE1_ARTIFACTS}",
      "catboost_secondary_model_dir": "${STAGE3_MODEL_DIR}",
      "catboost_secondary_artifacts_dir": "${STAGE3_ARTIFACTS}"
    }
  ]
}
PRESETS_EOF
ok "Model presets configured"

# ── 7. Startup script ─────────────────────────────────────────
START_SCRIPT="$INSTALL_DIR/start.sh"
cat > "$START_SCRIPT" <<SCRIPT_EOF
#!/usr/bin/env bash
INSTALL_DIR="\$(cd "\$(dirname "\$0")" && pwd)"
GUI_DIR="\$INSTALL_DIR/AnomalyNet-gui"
VENV="\$GUI_DIR/backend/.venv"
if [ "\$(id -u)" -ne 0 ]; then
    echo "Restarting with sudo (scapy requires root)..."
    exec sudo ANOMALYNET_APP_ROOT="\$GUI_DIR" "\$0" "\$@"
fi
echo ""
echo "  AnomalyNet started"
echo "  URL: http://\$(hostname -I | awk '{print \$1}'):8000"
echo ""
cd "\$GUI_DIR/backend"
exec "\$VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level warning
SCRIPT_EOF
chmod +x "$START_SCRIPT"

# ── 8. Systemd service ────────────────────────────────────────
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
Environment=ANOMALYNET_MODELS_ROOT=${MODEL_DIR}

[Install]
WantedBy=multi-user.target
SERVICE_EOF

sudo systemctl daemon-reload
sudo systemctl enable anomalynet 2>/dev/null || true
ok "Systemd service installed"

# ── Done ──────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
echo ""
echo "================================================"
echo "  Installation complete!"
echo ""
echo "  Start:   sudo $START_SCRIPT"
echo "  Service: sudo systemctl start anomalynet"
echo "  UI:      http://${IP}:8000"
echo ""
echo "  Logs:    journalctl -u anomalynet -f"
echo "================================================"
