#!/usr/bin/env bash
# AnomalyNet IDS — Linux Installer
# Run: bash install.sh
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/backend/.venv"
LAUNCHER="$APP_DIR/launch.sh"
ICON_PNG="$APP_DIR/frontend/public/logo.png"
DESKTOP_ENTRY_NAME="anomalynet.desktop"

echo ""
echo " ============================================================"
echo "  AnomalyNet IDS | Linux Installer"
echo " ============================================================"
echo ""

# ── Check Python ─────────────────────────────────────────────────
echo "[1/6] Checking Python..."
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo " [ERROR] Python 3.10+ not found. Install it first:"
    echo "         sudo apt install python3 python3-venv   # Debian/Ubuntu"
    echo "         sudo dnf install python3                # Fedora"
    exit 1
fi
echo "        $PYTHON $(${PYTHON} --version 2>&1)"

# ── Create virtual environment ───────────────────────────────────
echo "[2/6] Setting up virtual environment..."
if [ ! -f "$VENV_DIR/bin/python" ]; then
    $PYTHON -m venv "$VENV_DIR"
fi
echo "        OK"

# ── Install dependencies ─────────────────────────────────────────
echo "[3/6] Installing dependencies (may take a minute)..."
"$VENV_DIR/bin/pip" install -r "$APP_DIR/backend/requirements.txt" --quiet --disable-pip-version-check
echo "        OK"

# ── Make launcher executable ─────────────────────────────────────
chmod +x "$LAUNCHER"

# ── Create .desktop shortcut ─────────────────────────────────────
echo "[4/6] Creating application shortcuts..."

write_desktop() {
    local dest="$1"
    mkdir -p "$(dirname "$dest")"
    cat > "$dest" <<EOF
[Desktop Entry]
Name=AnomalyNet IDS
Comment=Network intrusion detection system
Exec=bash ${LAUNCHER}
Path=${APP_DIR}
Icon=${ICON_PNG}
Terminal=false
Type=Application
Categories=Network;Security;
StartupNotify=true
EOF
    chmod +x "$dest"
}

# Application menu
write_desktop "$HOME/.local/share/applications/$DESKTOP_ENTRY_NAME"

# Desktop (if exists)
if [ -d "$HOME/Desktop" ]; then
    write_desktop "$HOME/Desktop/$DESKTOP_ENTRY_NAME"
    echo "        Desktop shortcut created."
fi

command -v update-desktop-database &>/dev/null && \
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "        Added to applications menu."

# ── Add to autostart ─────────────────────────────────────────────
echo "[5/6] Adding to autostart..."
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/$DESKTOP_ENTRY_NAME" <<EOF
[Desktop Entry]
Name=AnomalyNet IDS
Exec=bash ${LAUNCHER}
Path=${APP_DIR}
Icon=${ICON_PNG}
Terminal=false
Type=Application
X-GNOME-Autostart-enabled=true
EOF
echo "        Added to autostart (~/.config/autostart, no sudo required)."

# ── Launch the app ───────────────────────────────────────────────
echo "[6/6] Starting AnomalyNet IDS..."
bash "$LAUNCHER" &

echo ""
echo " ============================================================"
echo "  Installation complete!"
echo ""
echo "  App menu shortcut: installed"
echo "  Autostart:         enabled"
echo "  To uninstall:      bash uninstall.sh"
echo " ============================================================"
echo ""
