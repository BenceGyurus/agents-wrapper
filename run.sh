#!/bin/bash
set -e

# Startup script for agents-wrapper (Ollama-compatible API)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "   🤖 agents-wrapper indítása (Ollama API átjáró)"
echo "=================================================="

# 1. Python 3 ellenőrzése
if ! command -v python3 &> /dev/null; then
    echo "❌ Hiba: A 'python3' nincs telepítve vagy nem található a PATH-ban!" >&2
    exit 1
fi

# Ha systemd service beállítást kértek
if [ "$1" = "--service" ] || [ "$1" = "--install-service" ]; then
    shift
    exec "$SCRIPT_DIR/setup-service.sh" "$@"
fi

# 2. Virtuális környezet (.venv) ellenőrzése és öngyógyítása
VENV_DIR="$SCRIPT_DIR/.venv"
RECREATE_VENV=false

if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/python" ]; then
    RECREATE_VENV=true
elif ! "$VENV_DIR/bin/python" -c "import sys" &> /dev/null; then
    echo "⚠️ A létező .venv sérült vagy más gépről lett átmásolva. Újraépítés..."
    rm -rf "$VENV_DIR"
    RECREATE_VENV=true
fi

if [ "$RECREATE_VENV" = true ]; then
    echo "📦 [1/3] Virtuális környezet (.venv) létrehozása..."
    if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
        echo "❌ Hiba: Nem sikerült létrehozni a virtuális környezetet!"
        echo "💡 Debian/Ubuntu gépen futtasd az alábbi parancsot, majd próbáld újra:"
        echo "   sudo apt update && sudo apt install -y python3-venv python3-pip"
        exit 1
    fi
else
    echo "✅ [1/3] Virtuális környezet (.venv) megtalálva."
fi

# Ellenőrizzük, hogy a pip elérhető-e a virtuális környezetben
if ! "$VENV_DIR/bin/python" -m pip --version &> /dev/null; then
    echo "⚙️ Pip inicializálása a virtuális környezetben (ensurepip)..."
    if ! "$VENV_DIR/bin/python" -m ensurepip --default-pip &> /dev/null; then
        echo "❌ A pip nem érhető el a virtuális környezetben!"
        echo "💡 Debian/Ubuntu gépen telepítsd: sudo apt update && sudo apt install -y python3-venv python3-pip"
        exit 1
    fi
fi

# 3. Pip frissítése és requirements telepítése (python -m pip használatával)
echo "📥 [2/3] Függőségek ellenőrzése és telepítése (requirements.txt)..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip -q
"$VENV_DIR/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.txt" -q
"$VENV_DIR/bin/python" -m pip install -e "$SCRIPT_DIR" -q

# 4. Szerver indítása
echo "🚀 [3/3] Szerver indítása..."
export PYTHONPATH="$SCRIPT_DIR"
exec "$VENV_DIR/bin/python" src/main.py "$@"
