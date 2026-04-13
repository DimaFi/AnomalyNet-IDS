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
#    PORT=8000               port to expose the web UI
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
PORT="${PORT:-8000}"

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
log "Port            : $PORT"
echo ""

# ── 0. Swap (critical for 2GB RAM — npm build needs ~1.5GB) ──
SWAP_FILE="/swapfile"
TOTAL_RAM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)
if [ "$TOTAL_RAM_MB" -lt 3500 ] && [ ! -f "$SWAP_FILE" ]; then
    log "Low RAM detected (${TOTAL_RAM_MB}MB). Creating 2GB swap..."
    sudo fallocate -l 2G "$SWAP_FILE" 2>/dev/null || sudo dd if=/dev/zero of="$SWAP_FILE" bs=1M count=2048 status=none
    sudo chmod 600 "$SWAP_FILE"
    sudo mkswap "$SWAP_FILE" -q
    sudo swapon "$SWAP_FILE"
    echo "$SWAP_FILE none swap sw 0 0" | sudo tee -a /etc/fstab > /dev/null
    ok "Swap created (2GB)"
else
    ok "Swap: OK (RAM=${TOTAL_RAM_MB}MB)"
fi

# ── 1. System dependencies ───────────────────────────────────
log "Installing system packages..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    # python3.10-venv is separate on Ubuntu 22.04 — must install explicitly
    sudo apt-get install -y -qq \
        python3 python3-pip python3-venv python3-dev python3-full \
        libpcap-dev libpcap0.8 \
        git curl wget \
        net-tools iproute2 \
        ufw 2>/dev/null || true

    # Node.js: install v20 via NodeSource (Ubuntu ships v12 which is too old)
    NODE_VER=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1 || echo "0")
    if [ "$NODE_VER" -lt 18 ]; then
        log "Installing Node.js 20 via NodeSource..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - 2>/dev/null
        sudo apt-get install -y -qq nodejs
    fi
elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3 python3-pip python3-devel libpcap libpcap-devel git curl
    # Node.js via NodeSource for RHEL/CentOS
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo dnf install -y nodejs
else
    err "Unsupported package manager. Install manually: python3, nodejs 20+, libpcap-dev, git"
fi

# Verify versions
PYTHON_VER=$(python3 --version 2>&1)
NODE_VER_FULL=$(node --version 2>&1)
ok "System packages: $PYTHON_VER | Node $(node --version)"

# ── 2. Open firewall port ─────────────────────────────────────
log "Configuring firewall (UFW port $PORT)..."
if command -v ufw &>/dev/null; then
    sudo ufw allow "$PORT/tcp" comment "AnomalyNet web UI" 2>/dev/null || true
    ok "UFW: port $PORT open"
fi

# ── 3. Clone / update repos ───────────────────────────────────
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

if [ -d "AnomalyNet-gui/.git" ]; then
    log "Updating AnomalyNet-gui..."
    git -C AnomalyNet-gui pull --quiet
else
    log "Cloning AnomalyNet-gui..."
    git clone --quiet --depth 1 "$GUI_REPO" AnomalyNet-gui
fi

if [ -d "$MODEL_DIR/.git" ]; then
    log "Updating AnomalyNet-ml..."
    git -C "$MODEL_DIR" pull --quiet
else
    log "Cloning AnomalyNet-ml (models — may take 1-2 min, ~120MB)..."
    # --depth 1 skips full git history; saves ~50MB and speeds up clone
    git clone --quiet --depth 1 "$ML_REPO" "$MODEL_DIR"
fi
ok "Repos ready"

# ── Model paths ───────────────────────────────────────────────
STAGE1_MODEL_DIR="$MODEL_DIR/model"
STAGE1_ARTIFACTS="$MODEL_DIR/artifacts"
STAGE2_MODEL_DIR="$MODEL_DIR/stage2_multiclass/models/catboost"
STAGE3_MODEL_DIR="$MODEL_DIR/stage3_cic2023/models/catboost"
STAGE3_ARTIFACTS="$MODEL_DIR/stage3_cic2023/artifacts"

# Verify critical model files exist
[ -d "$STAGE1_MODEL_DIR" ] || err "Stage1 model dir not found: $STAGE1_MODEL_DIR"
[ -d "$STAGE1_ARTIFACTS" ] || err "Stage1 artifacts dir not found: $STAGE1_ARTIFACTS"

# Select cascade model based on detection mode
if [ "$DETECTION_MODE" = "advanced" ]; then
    ACTIVE_MODEL_ID="catboost-cascade-advanced"
    SEC_MODEL_DIR="$STAGE3_MODEL_DIR"
    SEC_ARTIFACTS="$STAGE3_ARTIFACTS"
    [ -d "$STAGE3_MODEL_DIR" ] || err "Stage3 model dir not found: $STAGE3_MODEL_DIR (needed for advanced mode)"
else
    ACTIVE_MODEL_ID="catboost-cascade-simple"
    SEC_MODEL_DIR="$STAGE2_MODEL_DIR"
    SEC_ARTIFACTS=""
    [ -d "$STAGE2_MODEL_DIR" ] || err "Stage2 model dir not found: $STAGE2_MODEL_DIR (needed for simple mode)"
fi

# ── 4. Python venv + deps ─────────────────────────────────────
GUI_DIR="$INSTALL_DIR/AnomalyNet-gui"
VENV="$GUI_DIR/backend/.venv"

log "Setting up Python venv..."
# Prefer python3.11 if available; fall back to python3
PYTHON_BIN=$(command -v python3.11 || command -v python3.10 || command -v python3)
log "Using Python: $($PYTHON_BIN --version)"

"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip setuptools wheel
"$VENV/bin/pip" install --quiet -r "$GUI_DIR/backend/requirements.txt"
ok "Python dependencies installed"

# ── 5. Build frontend ─────────────────────────────────────────
log "Building React frontend (may take 2-3 min on low RAM)..."
cd "$GUI_DIR/frontend"
npm install --silent
# Limit Node.js heap to avoid OOM on 2GB VPS
NODE_OPTIONS="--max-old-space-size=1536" npm run build
ok "Frontend built"

# ── 6. Write settings.json ────────────────────────────────────
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

# ── 7. Update presets with actual paths ───────────────────────
log "Configuring model presets..."
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

# ── 8. Startup script ─────────────────────────────────────────
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
echo "  URL: http://\$(hostname -I | awk '{print \$1}'):${PORT}"
echo ""
export ANOMALYNET_APP_ROOT="\$GUI_DIR"
export ANOMALYNET_MODELS_ROOT="${MODEL_DIR}"
cd "\$GUI_DIR/backend"
exec "\$VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --log-level info
SCRIPT_EOF
chmod +x "$START_SCRIPT"

# ── 9. Systemd service ────────────────────────────────────────
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
ExecStart=${VENV}/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --log-level info
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
echo "  Manual start : sudo $START_SCRIPT"
echo "  Service start: sudo systemctl start anomalynet"
echo "  Service logs : journalctl -u anomalynet -f"
echo ""
echo "  Web UI       : http://${IP}:${PORT}"
echo "  API health   : http://${IP}:${PORT}/api/health"
echo "  Debug stats  : http://${IP}:${PORT}/api/debug/stats"
echo ""
echo "  Detection mode: ${DETECTION_MODE}"
echo "  Interface     : ${INTERFACE}"
echo "================================================"
