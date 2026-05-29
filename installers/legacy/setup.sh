#!/usr/bin/env bash
# AnomalyNet IDS — full install / update script
# Usage:
#   First install:  bash <(curl -s https://raw.githubusercontent.com/DimaFi/AnomalyNet-gui/main/setup.sh)
#   Update:         cd /opt/anomalynet && bash setup.sh
set -euo pipefail

APP_DIR=/opt/anomalynet
ML_DIR=/opt/anomalynet-ml
GUI_REPO=https://github.com/DimaFi/AnomalyNet-gui.git
ML_REPO=https://github.com/DimaFi/AnomalyNet-ml.git
SERVICE=anomalynet
PORT=8000

log()  { echo -e "\033[1;34m[AnomalyNet]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[OK]\033[0m $*"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()  { echo -e "\033[1;31m[ERR]\033[0m $*"; exit 1; }

[[ $EUID -ne 0 ]] && err "Запустите скрипт от root: sudo bash setup.sh"

# ── 1. System dependencies ──────────────────────────────────────────────────
log "Установка системных зависимостей..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip git curl iptables

# Node.js 20 LTS (needed for npm run build)
if ! command -v node &>/dev/null || [[ $(node -v | cut -d. -f1 | tr -d v) -lt 18 ]]; then
    log "Установка Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1
    apt-get install -y -qq nodejs
fi
ok "node $(node -v), npm $(npm -v)"

# ── 2. Clone or update GUI repo ─────────────────────────────────────────────
log "Репозиторий GUI..."
if [[ -d "$APP_DIR/.git" ]]; then
    git -C "$APP_DIR" pull --ff-only
    ok "GUI обновлён"
else
    git clone --depth=1 "$GUI_REPO" "$APP_DIR"
    ok "GUI клонирован"
fi

# ── 3. Clone or update ML repo ──────────────────────────────────────────────
log "Репозиторий ML (модели)..."
if [[ -d "$ML_DIR/.git" ]]; then
    git -C "$ML_DIR" pull --ff-only
    ok "ML обновлён"
else
    log "Клонирование ML репозитория (модели ~65 MB, это займёт время)..."
    git clone --depth=1 "$ML_REPO" "$ML_DIR"
    ok "ML клонирован"
fi

# ── 4. Python dependencies ───────────────────────────────────────────────────
log "Установка Python зависимостей..."
pip3 install -q -r "$APP_DIR/backend/requirements.txt"
ok "Python deps OK"

# ── 5. Build frontend ────────────────────────────────────────────────────────
log "Сборка фронтенда..."
cd "$APP_DIR/frontend"
npm install --silent
npm run build
ok "Frontend собран"
cd /

# ── 6. Auto-detect network interface ────────────────────────────────────────
IFACE=$(ip route get 8.8.8.8 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | head -1)
IFACE=${IFACE:-eth0}
log "Интерфейс: $IFACE"

# ── 7. Write settings.json ───────────────────────────────────────────────────
SETTINGS="$APP_DIR/config/settings.json"
mkdir -p "$APP_DIR/config"

python3 - <<PYEOF
import json, os

path = "$SETTINGS"
s = {}
if os.path.exists(path):
    try:
        s = json.load(open(path))
    except Exception:
        s = {}

s.setdefault("language", "ru")
s.setdefault("theme", "dark")
s.setdefault("retention_days", 14)
s.setdefault("capture_enabled", True)
s.setdefault("stream_autostart", True)
s.setdefault("catboost_threshold", 0.70)
s.setdefault("auto_block", False)
s.setdefault("auto_block_level", "anomaly")
s.setdefault("auto_unblock", True)
s.setdefault("auto_unblock_cooldown_min", 1)
s.setdefault("whitelist_ips", [])

# Always overwrite runtime/model settings
s.update({
    "run_mode":                        "linux_live",
    "active_model_id":                 "catboost-cascade-routed",
    "interface_name":                  "$IFACE",
    "interface_names":                 ["$IFACE"],
    "detection_mode":                  "simple",
    "catboost_model_dir":              "$ML_DIR/model",
    "preprocessing_artifacts_dir":     "$ML_DIR/artifacts",
    "catboost_secondary_model_dir":    "$ML_DIR/stage4_extended/models/catboost",
    "catboost_secondary_artifacts_dir":"$ML_DIR/stage4_extended/models/catboost",
    "catboost_stage3_model_dir":       "$ML_DIR/stage4_extended/models/catboost",
    "catboost_stage3_artifacts_dir":   "$ML_DIR/stage4_extended/models/catboost",
})

json.dump(s, open(path, "w"), indent=2, ensure_ascii=False)
print("settings.json OK")
PYEOF

# ── 8. Systemd service ───────────────────────────────────────────────────────
log "Настройка systemd сервиса..."
cat > /etc/systemd/system/$SERVICE.service <<SERVICE
[Unit]
Description=AnomalyNet IDS
After=network.target

[Service]
WorkingDirectory=$APP_DIR/backend
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable $SERVICE --quiet
systemctl restart $SERVICE
ok "Сервис запущен"

# ── 9. Health check ──────────────────────────────────────────────────────────
log "Проверка работоспособности..."
sleep 5
STATUS=$(systemctl is-active $SERVICE 2>/dev/null || echo "unknown")
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/ 2>/dev/null || echo "000")
IP=$(hostname -I | awk '{print $1}')

echo ""
echo "══════════════════════════════════════════"
ok "AnomalyNet IDS установлен/обновлён"
echo "  Сервис:    $STATUS"
echo "  HTTP:      $HTTP"
echo "  URL:       http://$IP:$PORT"
echo "  Интерфейс: $IFACE"
echo "══════════════════════════════════════════"
