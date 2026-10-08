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

# 2. Virtuális környezet (.venv) létrehozása, ha nem létezik vagy hibás
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "📦 [1/3] Virtuális környezet (.venv) létrehozása..."
    python3 -m venv "$VENV_DIR"
else
    echo "✅ [1/3] Virtuális környezet (.venv) megtalálva."
fi

# 3. Pip frissítése és requirements telepítése
echo "📥 [2/3] Függőségek ellenőrzése és telepítése (requirements.txt)..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
"$VENV_DIR/bin/pip" install -e "$SCRIPT_DIR" -q

# 4. Szerver indítása
echo "🚀 [3/3] Szerver indítása..."
export PYTHONPATH="$SCRIPT_DIR"
exec "$VENV_DIR/bin/python" src/main.py "$@"
