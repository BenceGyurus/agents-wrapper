#!/bin/bash
# Startup script for CLI Agent Wrapper (Ollama API compatible)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    ./.venv/bin/pip install -r requirements.txt
fi

echo "Starting CLI Agent Wrapper on port 11434..."
export PYTHONPATH="$SCRIPT_DIR"
exec ./.venv/bin/python src/main.py "$@"
