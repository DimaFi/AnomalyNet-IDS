#!/usr/bin/env bash
# ============================================================
#  AnomalyNet IDS — Linux Install Script
#  Tested on: Ubuntu 22.04/24.04, Debian 12, Alt Linux p10,
#             CentOS/RHEL 8+, Rocky Linux, Arch Linux
#
#  Usage:
#    sudo bash install.sh
#
#  Options (env vars):
#    INTERFACE=eth0          сетевой интерфейс для захвата
#    DETECTION_MODE=simple   "simple" (Stage1+Stage2) или "advanced" (Stage1+Stage3)
#    AUTO_BLOCK=false        автоматически блокировать атаки
#    PORT=8000               порт веб-интерфейса
#    INSTALL_DIR=/opt/anomalynet
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
log()  { echo -e "${CYAN}▶  $*${NC}"; }
ok()   { echo -e "${GREEN}✓  $*${NC}"; }
warn() { echo -e "${YELLOW}⚠  $*${NC}"; }
err()  { echo -e "${RED}✗  $*${NC}"; exit 1; }

# ── Параметры ────────────────────────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-/opt/anomalynet}"
GUI_REPO="https://github.com/DimaFi/AnomalyNet-gui.git"
ML_REPO="https://github.com/DimaFi/AnomalyNet-ml.git"
ML_DIR="$INSTALL_DIR/AnomalyNet-ml"
GUI_DIR="$INSTALL_DIR/AnomalyNet-gui"
MODELS_DIR="$INSTALL_DIR/models"
AUTO_BLOCK="${AUTO_BLOCK:-false}"
DETECTION_MODE="${DETECTION_MODE:-simple}"
PORT="${PORT:-8000}"

detect_interface() {
    ip -o link show | awk -F': ' '$2 !~ /lo|docker|br-|virbr/ {print $2; exit}'
}
INTERFACE="${INTERFACE:-$(detect_interface)}"

echo ""
echo -e "${BOLD}  ╔═══════════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║       AnomalyNet IDS — Установка      ║${NC}"
echo -e "${BOLD}  ╚═══════════════════════════════════════╝${NC}"
echo ""
log "Каталог установки : $INSTALL_DIR"
log "Каталог моделей   : $MODELS_DIR"
log "Интерфейс         : $INTERFACE"
log "Режим детекции    : $DETECTION_MODE"
log "Порт              : $PORT"
echo ""

[ $EUID -eq 0 ] || err "Запустите с правами root: sudo bash install.sh"

# ── Определение дистрибутива ─────────────────────────────────
detect_distro() {
    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        echo "${ID:-unknown}"
    elif [ -f /etc/redhat-release ]; then
        echo "rhel"
    else
        echo "unknown"
    fi
}
DISTRO=$(detect_distro)
log "Дистрибутив: $DISTRO"

# ── 0. Swap (для VPS с 2GB RAM — npm build требует ~1.5GB) ───
SWAP_FILE="/swapfile"
TOTAL_RAM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)
if [ "$TOTAL_RAM_MB" -lt 3500 ] && [ ! -f "$SWAP_FILE" ]; then
    log "Мало RAM (${TOTAL_RAM_MB}MB). Создаём swap 2GB..."
    fallocate -l 2G "$SWAP_FILE" 2>/dev/null || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=2048 status=none
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" -q
    swapon "$SWAP_FILE"
    echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
    ok "Swap создан (2GB)"
else
    ok "Память: OK (RAM=${TOTAL_RAM_MB}MB)"
fi

# ── 1. Системные пакеты ──────────────────────────────────────
log "Установка системных пакетов (дистро: $DISTRO)..."

_install_nodejs_nvm() {
    # Универсальный fallback через NVM (работает на любом дистро)
    log "Устанавливаем Node.js через NVM..."
    export NVM_DIR="/opt/nvm"
    mkdir -p "$NVM_DIR"
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | NVM_DIR="$NVM_DIR" bash 2>/dev/null
    # shellcheck disable=SC1090
    . "$NVM_DIR/nvm.sh"
    nvm install 20 --silent
    nvm alias default 20
    # Делаем node/npm глобально доступными
    NODE_BIN=$(nvm which 20)
    ln -sf "$NODE_BIN" /usr/local/bin/node
    ln -sf "$(dirname "$NODE_BIN")/npm" /usr/local/bin/npm
}

case "$DISTRO" in
    ubuntu|debian|linuxmint|raspbian|pop)
        apt-get update -qq
        apt-get install -y -qq \
            python3 python3-pip python3-venv python3-dev \
            libpcap-dev libpcap0.8 \
            git curl wget net-tools iproute2 ufw 2>/dev/null || true

        NODE_VER=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1 || echo "0")
        if [ "$NODE_VER" -lt 18 ]; then
            log "Устанавливаем Node.js 20 (nodesource)..."
            curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>/dev/null
            apt-get install -y -qq nodejs
        fi
        ;;

    altlinux|alt)
        # Alt Linux — RPM-based apt, имена пакетов отличаются
        apt-get update -q
        apt-get install -y \
            python3 python3-module-pip \
            libpcap-devel \
            git curl wget net-tools iproute2 2>/dev/null || true
        # python3-venv — устанавливается через pip если нет пакета
        python3 -m ensurepip --upgrade 2>/dev/null || true
        pip3 install --quiet virtualenv 2>/dev/null || true

        NODE_VER=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1 || echo "0")
        if [ "$NODE_VER" -lt 18 ]; then
            # NodeSource не поддерживает Alt нативно — используем NVM
            _install_nodejs_nvm
        fi
        ;;

    fedora)
        dnf install -y python3 python3-pip python3-devel libpcap libpcap-devel git curl
        NODE_VER=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1 || echo "0")
        if [ "$NODE_VER" -lt 18 ]; then
            curl -fsSL https://rpm.nodesource.com/setup_20.x | bash - 2>/dev/null
            dnf install -y nodejs
        fi
        ;;

    rhel|centos|rocky|almalinux|ol)
        PKG_MGR=$(command -v dnf 2>/dev/null || command -v yum)
        "$PKG_MGR" install -y python3 python3-pip python3-devel libpcap libpcap-devel git curl
        NODE_VER=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1 || echo "0")
        if [ "$NODE_VER" -lt 18 ]; then
            curl -fsSL https://rpm.nodesource.com/setup_20.x | bash - 2>/dev/null
            "$PKG_MGR" install -y nodejs
        fi
        ;;

    arch|manjaro|endeavouros|garuda)
        pacman -Sy --noconfirm python python-pip git curl libpcap nodejs npm
        ;;

    opensuse*|sles)
        zypper install -y python3 python3-pip python3-devel libpcap-devel git curl
        _install_nodejs_nvm
        ;;

    *)
        warn "Дистрибутив '$DISTRO' не распознан — пробуем apt-get..."
        if command -v apt-get &>/dev/null; then
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-venv libpcap-dev git curl 2>/dev/null || true
            NODE_VER=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1 || echo "0")
            [ "$NODE_VER" -lt 18 ] && _install_nodejs_nvm
        elif command -v dnf &>/dev/null; then
            dnf install -y python3 python3-pip python3-devel libpcap-devel git curl
            _install_nodejs_nvm
        else
            err "Не найден пакетный менеджер. Установите вручную: python3 pip nodejs>=18 libpcap git"
        fi
        ;;
esac

ok "Системные пакеты: Python $(python3 --version) | Node $(node --version)"

# ── 2. Открываем порт в UFW ──────────────────────────────────
if command -v ufw &>/dev/null; then
    ufw allow "$PORT/tcp" comment "AnomalyNet web UI" 2>/dev/null || true
    ok "UFW: порт $PORT открыт"
fi

# ── 3. Клонирование / обновление репозиториев ────────────────
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

if [ -d "AnomalyNet-gui/.git" ]; then
    log "Обновляем AnomalyNet-gui..."
    git -C AnomalyNet-gui stash 2>/dev/null || true
    git -C AnomalyNet-gui pull --quiet
else
    log "Клонируем AnomalyNet-gui..."
    git clone --quiet --depth 1 "$GUI_REPO" AnomalyNet-gui
fi

if [ -d "$ML_DIR/.git" ]; then
    log "Обновляем AnomalyNet-ml..."
    git -C "$ML_DIR" pull --quiet
else
    log "Клонируем AnomalyNet-ml (модели, ~120MB, 1-2 мин)..."
    git clone --quiet --depth 1 "$ML_REPO" "$ML_DIR"
fi
ok "Репозитории готовы"

# ── 4. Создание стандартной структуры моделей ────────────────
log "Создаём /opt/anomalynet/models/ ..."

mkdir -p "$MODELS_DIR/stage1/catboost"
mkdir -p "$MODELS_DIR/stage1/artifacts"
mkdir -p "$MODELS_DIR/stage2/catboost"
mkdir -p "$MODELS_DIR/stage3/catboost"
mkdir -p "$MODELS_DIR/stage3/artifacts"

# Копируем модели из ML-репо в стандартные пути
copy_dir() {
    local src="$1" dst="$2" label="$3"
    if [ -d "$src" ] && [ "$(ls -A "$src" 2>/dev/null)" ]; then
        cp -r "$src/." "$dst/"
        ok "$label"
    else
        warn "$label — не найдено в $src (положите файлы вручную)"
    fi
}

copy_dir "$ML_DIR/model"        "$MODELS_DIR/stage1/catboost"  "Stage1 модель (binary)"
copy_dir "$ML_DIR/artifacts"    "$MODELS_DIR/stage1/artifacts" "Stage1 артефакты"
copy_dir "$ML_DIR/stage2_multiclass/models/catboost" "$MODELS_DIR/stage2/catboost"  "Stage2 модель (simple, 71 признак)"
copy_dir "$ML_DIR/stage3_cic2023/models/catboost"   "$MODELS_DIR/stage3/catboost"   "Stage3 модель (advanced, 46 признаков)"
copy_dir "$ML_DIR/stage3_cic2023/artifacts"         "$MODELS_DIR/stage3/artifacts"  "Stage3 артефакты"

echo ""
echo "   Структура моделей:"
echo "   $MODELS_DIR/"
echo "   ├── stage1/catboost/   ← model.cbm (бинарный детектор)"
echo "   ├── stage1/artifacts/  ← scaler.joblib, preprocessing_params.json"
echo "   ├── stage2/catboost/   ← model_mc.cbm (8 классов, Simple)"
echo "   ├── stage3/catboost/   ← model.cbm (8 классов IoT2023, Advanced)"
echo "   └── stage3/artifacts/  ← артефакты предобработки"
echo ""

# Проверяем есть ли модели (stage1 — обязательна)
STAGE1_HAS_MODEL=false
if compgen -G "$MODELS_DIR/stage1/catboost/*.cbm" > /dev/null 2>&1; then
    STAGE1_HAS_MODEL=true
fi

# ── 5. Выбор конфигурации по режиму ─────────────────────────
if [ "$STAGE1_HAS_MODEL" = false ]; then
    warn "Файлы моделей не найдены — запускаем в Demo-режиме (mock)"
    ACTIVE_MODEL_ID="mock-default"
    RUN_MODE="mock"
    DETECTION_MODE="simple"
    SEC_MODEL_DIR=""
    SEC_ARTIFACTS=""
elif [ "$DETECTION_MODE" = "advanced" ]; then
    ACTIVE_MODEL_ID="catboost-cascade-advanced"
    RUN_MODE="linux_live"
    SEC_MODEL_DIR="$MODELS_DIR/stage3/catboost"
    SEC_ARTIFACTS="$MODELS_DIR/stage3/artifacts"
else
    ACTIVE_MODEL_ID="catboost-cascade-simple"
    RUN_MODE="linux_live"
    DETECTION_MODE="simple"
    SEC_MODEL_DIR="$MODELS_DIR/stage2/catboost"
    SEC_ARTIFACTS=""
fi

ok "Режим: $RUN_MODE / $DETECTION_MODE / $ACTIVE_MODEL_ID"

# ── 6. Python venv + зависимости ────────────────────────────
VENV="$GUI_DIR/backend/.venv"
log "Настройка Python-окружения..."
PYTHON_BIN=$(command -v python3.11 2>/dev/null || command -v python3.10 2>/dev/null || command -v python3)
log "Python: $($PYTHON_BIN --version)"
"$PYTHON_BIN" -m venv "$VENV" 2>/dev/null || \
    { pip3 install --quiet virtualenv 2>/dev/null; virtualenv -p "$PYTHON_BIN" "$VENV"; }
"$VENV/bin/pip" install --quiet --upgrade pip setuptools wheel
"$VENV/bin/pip" install --quiet -r "$GUI_DIR/backend/requirements.txt"
ok "Python-зависимости установлены"

# ── 7. Сборка фронтенда ──────────────────────────────────────
log "Сборка React-фронтенда (2-3 мин на слабом сервере)..."
cd "$GUI_DIR/frontend"
# Удаляем node_modules и lock-файл чтобы избежать rollup-бага npm (optional deps)
rm -rf node_modules package-lock.json
npm install --silent
NODE_OPTIONS="--max-old-space-size=1536" npm run build
ok "Фронтенд собран"

# ── 8. Запись settings.json ──────────────────────────────────
log "Запись config/settings.json..."
cat > "$GUI_DIR/config/settings.json" <<SETTINGS_EOF
{
  "language": "ru",
  "theme": "dark",
  "run_mode": "${RUN_MODE}",
  "retention_days": 14,
  "active_model_id": "${ACTIVE_MODEL_ID}",
  "capture_enabled": true,
  "stream_autostart": true,
  "interface_name": "${INTERFACE}",
  "catboost_threshold": 0.70,
  "catboost_model_dir": "${MODELS_DIR}/stage1/catboost",
  "preprocessing_artifacts_dir": "${MODELS_DIR}/stage1/artifacts",
  "auto_block": ${AUTO_BLOCK},
  "auto_block_level": "anomaly",
  "whitelist_ips": [],
  "detection_mode": "${DETECTION_MODE}",
  "catboost_secondary_model_dir": "${SEC_MODEL_DIR}",
  "catboost_secondary_artifacts_dir": "${SEC_ARTIFACTS}"
}
SETTINGS_EOF
ok "settings.json записан (режим: $DETECTION_MODE, интерфейс: $INTERFACE)"

# ── 9. Синхронизация models_registry.json ───────────────────
log "Синхронизация реестра моделей..."
"$PYTHON_BIN" - <<PYEOF
import json, pathlib
p = pathlib.Path("$GUI_DIR/config/models_registry.json")
data = json.loads(p.read_text())
data["active_model_id"] = "${ACTIVE_MODEL_ID}"
for item in data.get("items", []):
    item["status"] = "active" if item["model_id"] == "${ACTIVE_MODEL_ID}" else "idle"
p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
PYEOF
ok "Реестр моделей обновлён (активная: ${ACTIVE_MODEL_ID})"

# ── 10. Обновление путей в model_presets.json ────────────────
log "Обновление пресетов моделей..."
cat > "$GUI_DIR/config/model_presets.json" <<PRESETS_EOF
{
  "presets": [
    {
      "id": "mock",
      "name": "Demo (без захвата)",
      "description": "Демо-режим: генерирует случайные события для ознакомления с интерфейсом. Не требует прав root и реального трафика.",
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
      "name": "Быстрый детектор (только атака/норма)",
      "description": "Определяет: атака или нет. Высокая скорость, F1=99.4%. Не показывает тип атаки. Минимальная нагрузка на систему.",
      "icon": "binary",
      "active_model_id": "catboost-iot-v1",
      "run_mode": "linux_live",
      "detection_mode": "simple",
      "catboost_model_dir": "${MODELS_DIR}/stage1/catboost",
      "preprocessing_artifacts_dir": "${MODELS_DIR}/stage1/artifacts",
      "catboost_secondary_model_dir": "",
      "catboost_secondary_artifacts_dir": ""
    },
    {
      "id": "simple-cascade",
      "name": "Simple — обнаружение + тип атаки",
      "description": "Сначала фильтрует трафик (атака/норма), затем определяет тип: DoS, DDoS, Recon, BruteForce и др. Стандартный режим.",
      "icon": "simple",
      "active_model_id": "catboost-cascade-simple",
      "run_mode": "linux_live",
      "detection_mode": "simple",
      "catboost_model_dir": "${MODELS_DIR}/stage1/catboost",
      "preprocessing_artifacts_dir": "${MODELS_DIR}/stage1/artifacts",
      "catboost_secondary_model_dir": "${MODELS_DIR}/stage2/catboost",
      "catboost_secondary_artifacts_dir": ""
    },
    {
      "id": "advanced-cascade",
      "name": "Advanced — улучшенная классификация IoT",
      "description": "Расширенный набор признаков для IoT-трафика. Значительно точнее на Recon, Bot и Spoofing. Macro F1=0.82 vs 0.31 у Simple.",
      "icon": "advanced",
      "active_model_id": "catboost-cascade-advanced",
      "run_mode": "linux_live",
      "detection_mode": "advanced",
      "catboost_model_dir": "${MODELS_DIR}/stage1/catboost",
      "preprocessing_artifacts_dir": "${MODELS_DIR}/stage1/artifacts",
      "catboost_secondary_model_dir": "${MODELS_DIR}/stage3/catboost",
      "catboost_secondary_artifacts_dir": "${MODELS_DIR}/stage3/artifacts"
    }
  ]
}
PRESETS_EOF
ok "Пресеты моделей обновлены"

# ── 11. Systemd-сервис ───────────────────────────────────────
log "Настройка systemd-сервиса..."
SERVICE="/etc/systemd/system/anomalynet.service"
cat > "$SERVICE" <<SERVICE_EOF
[Unit]
Description=AnomalyNet IDS
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${GUI_DIR}/backend
ExecStart=${VENV}/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --log-level info --timeout-graceful-shutdown 3
Restart=on-failure
RestartSec=3
TimeoutStopSec=8
KillMode=mixed
Environment=ANOMALYNET_APP_ROOT=${GUI_DIR}

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
systemctl enable anomalynet 2>/dev/null || true
systemctl restart anomalynet
sleep 2

if systemctl is-active --quiet anomalynet; then
    ok "Сервис запущен"
else
    warn "Сервис не запустился. Проверьте: journalctl -u anomalynet -n 30"
fi

# ── Итог ─────────────────────────────────────────────────────
IP=$(ip -4 addr show scope global | awk '/inet / {print $2}' | cut -d/ -f1 | head -1)
echo ""
echo -e "${BOLD}  ╔═══════════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║        Установка завершена!           ║${NC}"
echo -e "${BOLD}  ╚═══════════════════════════════════════╝${NC}"
echo ""
echo -e "  Веб-интерфейс : ${GREEN}http://${IP}:${PORT}${NC}"
echo -e "  API health    : http://${IP}:${PORT}/api/health"
echo ""
echo "  Режим детекции : $DETECTION_MODE"
echo "  Интерфейс      : $INTERFACE"
echo "  Модели в       : $MODELS_DIR/"
echo ""
if [ "$STAGE1_HAS_MODEL" = false ]; then
echo -e "  ${YELLOW}⚠  Модели не найдены — сейчас работает Demo-режим.${NC}"
echo    "  Чтобы включить live-захват, скопируйте модели в:"
echo    "    $MODELS_DIR/stage1/catboost/  ← model.cbm"
echo    "    $MODELS_DIR/stage1/artifacts/ ← scaler.joblib, preprocessing_params.json"
echo    "    $MODELS_DIR/stage2/catboost/  ← model_mc.cbm (для Simple)"
echo    "  И в Settings выберите конфигурацию модели."
fi
echo ""
echo "  Управление сервисом:"
echo "    systemctl start anomalynet"
echo "    systemctl stop anomalynet"
echo "    journalctl -u anomalynet -f"
echo ""
