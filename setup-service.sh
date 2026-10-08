#!/bin/bash
set -e

# Setup script for installing agents-wrapper as a systemd service on Debian/Linux

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "   ⚙️  agents-wrapper systemd szolgáltatás beállítása"
echo "=========================================================="

# 1. Alapvető elérési utak és felhasználó detektálása
RUN_USER="${SUDO_USER:-$USER}"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
MAIN_SCRIPT="$SCRIPT_DIR/src/main.py"
SERVICE_NAME="agents-wrapper.service"
SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME"

# Ellenőrizzük, hogy a venv létezik-e és működőképes-e
if [ ! -f "$VENV_PYTHON" ] || ! "$VENV_PYTHON" -c "import sys" &> /dev/null; then
    echo "📦 Virtuális környezet előkészítése / újragenerálása..."
    rm -rf "$SCRIPT_DIR/.venv"
    if ! python3 -m venv "$SCRIPT_DIR/.venv" 2>/dev/null; then
        echo "❌ Hiba a venv létrehozásakor! Telepítsd: sudo apt update && sudo apt install -y python3-venv python3-pip"
        exit 1
    fi
fi

# Pip és csomagok telepítése python -m pip használatával
"$VENV_PYTHON" -m pip install --upgrade pip -q
"$VENV_PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt" -q
"$VENV_PYTHON" -m pip install -e "$SCRIPT_DIR" -q

# PATH összerakása, hogy a CLI-k (agy, codex) elérhetők legyenek systemd alatt
CAPTURED_PATH="$PATH:/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:/home/$RUN_USER/.local/bin"

echo "📍 Munkakönyvtár : $SCRIPT_DIR"
echo "👤 Futtató felhasználó: $RUN_USER"
echo "🐍 Python bináris : $VENV_PYTHON"

# 2. Systemd service tartalom generálása
SERVICE_CONTENT="[Unit]
Description=agents-wrapper (Ollama-compatible API Gateway for AI CLI Agents)
Documentation=https://github.com/BenceGyurus/agents-wrapper
After=network.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$VENV_PYTHON -m src.main --host 0.0.0.0 --port 11434
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=\"PATH=$CAPTURED_PATH\"
StandardOutput=journal
StandardError=journal
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target"

# 3. Ellenőrzés: Linux rendszer és systemctl megléte
if ! command -v systemctl &> /dev/null; then
    echo ""
    echo "⚠️  Figyelem: A 'systemctl' nem található ezen a gépen (pl. macOS-en vagy konténerben vagy)."
    echo "📄 A generált systemd unit fájl mentve ide: $SCRIPT_DIR/$SERVICE_NAME"
    echo "$SERVICE_CONTENT" > "$SCRIPT_DIR/$SERVICE_NAME"
    echo ""
    echo "Debian/Linux gépre másolva az alábbi parancsokkal aktiválhatod:"
    echo "  sudo cp $SERVICE_NAME /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable --now $SERVICE_NAME"
    exit 0
fi

# 4. Telepítés /etc/systemd/system alá (root jogosultság szükséges)
echo "📝 Szolgáltatás fájl létrehozása: $SERVICE_FILE_PATH..."
if [ "$EUID" -ne 0 ]; then
    # Nem root, sudo-val írjuk
    echo "$SERVICE_CONTENT" | sudo tee "$SERVICE_FILE_PATH" > /dev/null
    sudo chmod 644 "$SERVICE_FILE_PATH"
    
    echo "🔄 Systemd újratöltése és aktiválás..."
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl restart "$SERVICE_NAME"
else
    # Root felhasználó
    echo "$SERVICE_CONTENT" > "$SERVICE_FILE_PATH"
    chmod 644 "$SERVICE_FILE_PATH"
    
    echo "🔄 Systemd újratöltése és aktiválás..."
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl restart "$SERVICE_NAME"
fi

echo ""
echo "✅ A szolgáltatás sikeresen beállítva és elindítva!"
echo "----------------------------------------------------------"
echo "Állapot ellenőrzése:"
echo "  sudo systemctl status $SERVICE_NAME"
echo ""
echo "Valós idejű naplók megtekintése:"
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "Leállítás / Újraindítás:"
echo "  sudo systemctl restart $SERVICE_NAME"
echo "  sudo systemctl stop $SERVICE_NAME"
echo "----------------------------------------------------------"
