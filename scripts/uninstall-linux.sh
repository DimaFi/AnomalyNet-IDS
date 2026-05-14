#!/usr/bin/env bash
# ============================================================
#  AnomalyNet IDS — Linux Uninstall Script
#
#  Usage:
#    sudo bash scripts/uninstall-linux.sh            # удалить код и сервис
#    sudo bash scripts/uninstall-linux.sh --purge    # + удалить /opt/anomalynet
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
log()  { echo -e "${CYAN}▶  $*${NC}"; }
ok()   { echo -e "${GREEN}✓  $*${NC}"; }
warn() { echo -e "${YELLOW}⚠  $*${NC}"; }
err()  { echo -e "${RED}✗  $*${NC}"; exit 1; }

INSTALL_DIR="${INSTALL_DIR:-/opt/anomalynet}"
PURGE=false
for arg in "$@"; do
    case "$arg" in --purge|-p) PURGE=true ;; esac
done

[ $EUID -eq 0 ] || err "Запустите с правами root: sudo bash scripts/uninstall-linux.sh"

echo ""
echo -e "${BOLD}  ╔════════════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║     AnomalyNet IDS — Удаление         ║${NC}"
echo -e "${BOLD}  ╚════════════════════════════════════════╝${NC}"
echo ""
if [ "$PURGE" = true ]; then
    warn "Режим --purge: будет удалено всё, включая $INSTALL_DIR"
fi
echo ""

# ── 1. Остановка и удаление сервиса ─────────────────────────
log "Остановка и удаление systemd-сервиса..."
if systemctl is-active --quiet anomalynet 2>/dev/null; then
    systemctl stop anomalynet
    ok "Сервис остановлен"
else
    warn "Сервис не запущен (или не найден)"
fi

if systemctl is-enabled --quiet anomalynet 2>/dev/null; then
    systemctl disable anomalynet 2>/dev/null || true
    ok "Сервис отключён из автозапуска"
fi

SERVICE="/etc/systemd/system/anomalynet.service"
if [ -f "$SERVICE" ]; then
    rm -f "$SERVICE"
    systemctl daemon-reload
    ok "Файл сервиса удалён: $SERVICE"
else
    warn "Файл сервиса не найден: $SERVICE"
fi

# ── 2. Удаление правил iptables (ANOMALYNET цепочки) ─────────
log "Удаление iptables-правил AnomalyNet..."
if command -v iptables &>/dev/null; then
    for CHAIN in ANOMALYNET_INPUT ANOMALYNET_FORWARD; do
        # Убираем jump-правило из INPUT / FORWARD
        PARENT=$(echo "$CHAIN" | sed 's/ANOMALYNET_//')
        iptables -D "$PARENT" -j "$CHAIN" 2>/dev/null && ok "Удалён jump из $PARENT → $CHAIN" || true
        # Очищаем и удаляем цепочку
        iptables -F "$CHAIN" 2>/dev/null || true
        iptables -X "$CHAIN" 2>/dev/null && ok "Цепочка $CHAIN удалена" || true
    done
else
    warn "iptables не найден — пропускаем удаление правил"
fi

# ── 3. Удаление правила UFW ───────────────────────────────────
if command -v ufw &>/dev/null; then
    PORT=$(python3 -c "
import json, pathlib
p = pathlib.Path('$INSTALL_DIR/AnomalyNet-gui/config/settings.json')
print(json.loads(p.read_text()).get('port', 8000) if p.exists() else 8000)
" 2>/dev/null || echo "8000")
    ufw delete allow "$PORT/tcp" 2>/dev/null && ok "UFW: правило порта $PORT удалено" || true
fi

# ── 4. Удаление файлов (опционально --purge) ─────────────────
if [ "$PURGE" = true ]; then
    log "Удаление каталога установки $INSTALL_DIR..."
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        ok "Удалено: $INSTALL_DIR"
    else
        warn "$INSTALL_DIR не найден"
    fi
else
    warn "Каталог $INSTALL_DIR сохранён (используйте --purge для полного удаления)"
    warn "Настройки и данные: $INSTALL_DIR/AnomalyNet-gui/config/"
fi

# ── Итог ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  ╔════════════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║        Удаление завершено!             ║${NC}"
echo -e "${BOLD}  ╚════════════════════════════════════════╝${NC}"
echo ""
if [ "$PURGE" = false ]; then
    echo "  Данные сохранены в: $INSTALL_DIR/"
    echo "  Для полного удаления: sudo bash scripts/uninstall-linux.sh --purge"
fi
echo ""
